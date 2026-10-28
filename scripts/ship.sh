#!/usr/bin/env bash
# Ship the current lane branch: take in main, test, push the branch, then move
# main to it and push main. Every lane ships this way, so main always holds all
# lanes and any lane can be merged into any other. See docs/branching.md.
#
#   scripts/ship.sh               # from a lane worktree (classic, studio, voice-room)
#   scripts/ship.sh --skip-tests  # only when the suite already ran on this commit
set -euo pipefail

skip_tests=0
if [[ "${1:-}" == "--skip-tests" ]]; then
  skip_tests=1
fi

branch=$(git rev-parse --abbrev-ref HEAD)
case "$branch" in
  main|HEAD)
    echo "Run this on a lane branch (classic, studio or voice-room), not '$branch'." >&2
    exit 1
    ;;
esac
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Commit your changes on '$branch' first." >&2
  exit 1
fi

# The origin remote is SSH, and this Mac's SSH key is not on GitHub. Talk HTTPS
# with the gh login instead, without changing the remote.
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

echo "-> Taking in main and any newer '$branch' from GitHub"
for ref in "origin/$branch" origin/main main; do
  if git rev-parse -q --verify "$ref" >/dev/null; then
    if ! git merge --no-edit "$ref"; then
      echo "Merge conflict with $ref. Resolve it on '$branch', commit, and run ship again." >&2
      exit 1
    fi
  fi
done

echo "-> Checking JavaScript syntax"
if command -v node >/dev/null 2>&1; then
  find static -name '*.js' -print0 | xargs -0 -n1 node --check
else
  echo "   node is not installed; skipped."
fi

if [[ "$skip_tests" -eq 0 ]]; then
  echo "-> Running the test suite (includes tests/test_classic_guard.py)"
  python3 -m pytest -q -p no:cacheprovider
fi

echo "-> Pushing '$branch'"
net push "$url" "HEAD:refs/heads/$branch"

echo "-> Moving main to '$branch'"
main_tree=""
while read -r key value; do
  if [[ "$key" == "worktree" ]]; then
    tree="$value"
  elif [[ "$key" == "branch" && "$value" == "refs/heads/main" ]]; then
    main_tree="$tree"
  fi
done < <(git worktree list --porcelain)
if [[ -n "$main_tree" ]]; then
  if [[ -n "$(git -C "$main_tree" status --porcelain --untracked-files=no)" ]]; then
    echo "The main checkout ($main_tree) has uncommitted changes; main was not moved." >&2
    echo "'$branch' is pushed. Clean that checkout, then run ship again." >&2
    exit 1
  fi
  git -C "$main_tree" merge --ff-only "$branch"
else
  git merge-base --is-ancestor main "$branch"
  git branch -f main "$branch"
fi

echo "-> Pushing main"
net push "$url" "refs/heads/main:refs/heads/main"
echo "Shipped '$branch' and main at $(git rev-parse --short HEAD)."
