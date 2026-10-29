#!/usr/bin/env bash
# Ship this lane's own branch (docs/branching.md).
#
# classic, voice-room: take in any newer copy of this lane from GitHub, check,
#   test, push the lane. They never merge main or studio in; studio takes
#   them in with scripts/integrate.sh.
# studio: the same, then fast-forward main (the archive) to studio and push it.
#
#   scripts/ship.sh               # from the lane's worktree
#   scripts/ship.sh --skip-tests  # only when the suite already ran on this commit
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
source scripts/lane.sh

skip_tests=0
if [[ "${1:-}" == "--skip-tests" ]]; then
  skip_tests=1
fi

branch=$(git rev-parse --abbrev-ref HEAD)
lane_env "$branch"
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Commit your changes on '$branch' first." >&2
  exit 1
fi
url=$(lane_url)

echo "-> Fetching GitHub"
net fetch -q "$url" '+refs/heads/*:refs/remotes/origin/*'
if git rev-parse -q --verify "origin/$branch" >/dev/null; then
  echo "-> Taking in any newer '$branch' from GitHub"
  if ! git merge --no-edit "origin/$branch"; then
    echo "Merge conflict with origin/$branch. Resolve it, commit, and run ship again." >&2
    exit 1
  fi
fi

if [[ "$skip_tests" -eq 0 ]]; then
  lane_checks
fi

echo "-> Pushing '$branch'"
net push "$url" "HEAD:refs/heads/$branch"

if [[ "$branch" != "studio" ]]; then
  echo "Shipped '$branch' at $(git rev-parse --short HEAD). Studio takes it in with scripts/integrate.sh."
  exit 0
fi

echo "-> Moving main (the archive) to studio"
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
    exit 1
  fi
  git -C "$main_tree" merge --ff-only studio
else
  git merge-base --is-ancestor main studio
  git branch -f main studio
fi
net push "$url" "refs/heads/main:refs/heads/main"
echo "Shipped studio and main at $(git rev-parse --short HEAD)."
