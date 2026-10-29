#!/usr/bin/env bash
# Ship studio, the integration lane, and move main (the archive) to it
# (docs/branching.md). Classic and Voice Room ship with scripts/ship-lane.sh
# and never move main.
#
#   scripts/ship.sh               # from the studio worktree
#   scripts/ship.sh --skip-tests  # only when the suite already ran on this commit
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

skip_tests=0
if [[ "${1:-}" == "--skip-tests" ]]; then
  skip_tests=1
fi

branch=$(git rev-parse --abbrev-ref HEAD)
if [[ "$branch" != "studio" ]]; then
  echo "scripts/ship.sh ships studio and moves main; this checkout is on '$branch'." >&2
  echo "Classic and Voice Room ship with scripts/ship-lane.sh." >&2
  exit 1
fi
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Commit your changes on studio first." >&2
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
if git rev-parse -q --verify origin/studio >/dev/null; then
  echo "-> Taking in any newer studio from GitHub"
  if ! git merge --no-edit origin/studio; then
    echo "Merge conflict with origin/studio. Resolve it, commit, and run ship again." >&2
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
  echo "-> Running the test suite (includes the Classic guard and Voice Room tests)"
  python3 -m pytest -q -p no:cacheprovider
fi

echo "-> Pushing studio"
net push "$url" "HEAD:refs/heads/studio"

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
