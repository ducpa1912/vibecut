# Lane table, sourced by the other scripts. Each lane has its own port, build
# switches, data folder and notes folder, and shares none of them with another
# lane (docs/branching.md).
#
#   source scripts/lane.sh; lane_env studio   # sets LANE_* for that lane

lane_env() {
  case "$1" in
    studio)
      LANE_PORT=8795; LANE_EDITION=all; LANE_FEATURES=voice_room ;;
    classic)
      LANE_PORT=8796; LANE_EDITION=classic; LANE_FEATURES= ;;
    voice-room)
      LANE_PORT=8797; LANE_EDITION=classic; LANE_FEATURES=voice_room ;;
    *)
      echo "'$1' is not a lane. Lanes: studio, classic, voice-room." >&2
      return 1 ;;
  esac
  LANE="$1"
  LANE_ROOT=$(git rev-parse --show-toplevel)
  LANE_DATA="$LANE_ROOT/data"
  LANE_NOTES="$LANE_ROOT/.lane"
}

# The origin remote is SSH, and this Mac's SSH key is not on GitHub. Talk HTTPS
# with the gh login instead, without changing the remote.
lane_url() {
  local origin
  origin=$(git remote get-url origin)
  case "$origin" in
    git@github.com:*) echo "https://github.com/${origin#git@github.com:}" ;;
    *) echo "$origin" ;;
  esac
}

net() {
  if command -v gh >/dev/null 2>&1; then
    git -c credential.helper= -c 'credential.helper=!gh auth git-credential' "$@"
  else
    git "$@"
  fi
}

lane_checks() {
  echo "-> Checking JavaScript syntax"
  if command -v node >/dev/null 2>&1; then
    find static -name '*.js' -print0 | xargs -0 -n1 node --check
  else
    echo "   node is not installed; skipped."
  fi
  echo "-> Running the test suite (includes the Classic guard and Voice Room tests)"
  python3 -m pytest -q -p no:cacheprovider
}
