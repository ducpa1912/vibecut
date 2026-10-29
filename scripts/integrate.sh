#!/usr/bin/env bash
# Studio only: take in the latest classic and voice-room, check that both still
# work inside studio, then ship studio and main (docs/branching.md).
#
# Run it only when studio has finished and shipped its own latest change.
#
#   scripts/integrate.sh     # from the studio worktree
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

branch=$(git rev-parse --abbrev-ref HEAD)
if [[ "$branch" != "studio" ]]; then
  echo "Only the studio lane integrates; this checkout is on '$branch'." >&2
  exit 1
fi
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Studio has uncommitted work. Finish and ship it first." >&2
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
before=$(git rev-parse HEAD)
for ref in origin/studio origin/classic origin/voice-room; do
  if git rev-parse -q --verify "$ref" >/dev/null; then
    echo "-> Merging $ref into studio"
    if ! git merge --no-edit "$ref"; then
      echo "Merge conflict with $ref. Resolve it on studio, keeping both lanes working, commit, and run integrate again." >&2
      exit 1
    fi
  fi
done

if [[ "$(git rev-parse HEAD)" == "$before" ]]; then
  echo "Nothing new from classic or voice-room."
else
  echo "-> Came in:"
  git log --oneline --no-merges "$before"..HEAD | sed 's/^/   /'
  echo "-> Classic and Voice Room checks first"
  guards=(tests/test_classic_guard.py tests/test_editions.py tests/test_voice_clone.py tests/test_voice_extract.py)
  [[ -f tests/test_lane_isolation.py ]] && guards+=(tests/test_lane_isolation.py)
  python3 -m pytest -q -p no:cacheprovider "${guards[@]}"
fi

exec scripts/ship.sh
