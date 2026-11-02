#!/usr/bin/env bash
# Ship a lane branch without moving main. A main release is a separate,
# explicit scripts/ship.sh --release-main decision.
#
#   scripts/ship-lane.sh               # from a lane worktree
#   scripts/ship-lane.sh --skip-tests  # only when the suite already ran
#
# Every lane keeps its own port, data folder and media folder. See
# scripts/lane-env.sh and docs/shared/branching.md.
set -euo pipefail

skip_tests=0
if [[ "${1:-}" == "--skip-tests" ]]; then
  skip_tests=1
fi

branch=$(git rev-parse --abbrev-ref HEAD)
case "$branch" in
  classic|classic-b|studio|voice-room) ;;
  *)
    echo "Run this on a Classic, Studio or Voice Room branch, not '$branch'." >&2
    echo "A main release uses scripts/ship.sh --release-main." >&2
    exit 1
    ;;
esac
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Commit your changes on '$branch' first." >&2
  exit 1
fi

origin=$(git remote get-url origin)
case "$origin" in
  git@github.com:*) url="https://github.com/${origin#git@github.com:}" ;;
  *) url="$origin" ;;
esac
net() {
  if command -v gh >/dev/null 2>&1; then
    git -c credential.helper= -c 'credential.helper=!gh auth git-credential' "$@"
  else
    git "$@"
  fi
}

echo "-> Fetching GitHub"
net fetch -q "$url" '+refs/heads/*:refs/remotes/origin/*'

if git rev-parse -q --verify "origin/$branch" >/dev/null; then
  echo "-> Taking in newer '$branch' from GitHub"
  if ! git merge --no-edit "origin/$branch"; then
    echo "Merge conflict with origin/$branch. Resolve it on '$branch', commit, and run again." >&2
    exit 1
  fi
fi

echo "-> Checking JavaScript syntax"
if command -v node >/dev/null 2>&1; then
  find static -name '*.js' -print0 | xargs -0 -n1 node --check
else
  echo "   node is not installed; skipped."
fi

if [[ "$skip_tests" -eq 0 ]]; then
  echo "-> Running the test suite"
  python3 -m pytest -q -p no:cacheprovider
fi

if ! git verify-commit HEAD >/dev/null 2>&1; then
  echo "HEAD is not signed. Sign the commit before shipping." >&2
  exit 1
fi

echo "-> Pushing '$branch' (main is not moved)"
net push "$url" "HEAD:refs/heads/$branch"
echo "Shipped '$branch' at $(git rev-parse --short HEAD). Main was not moved."
