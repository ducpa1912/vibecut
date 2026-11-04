#!/usr/bin/env bash
# Tag the shipped classic lane as a beta release and push the tag.
# Beta testers get tags, never a branch tip (docs/shared/branching.md, Phase C).
#
#   scripts/release.sh --founder-passed            # tag and push beta-YYYYMMDD-N
#   scripts/release.sh --founder-passed --dry-run  # say what it would tag
#
# Run it from the classic worktree after the founder test pass is clean.
set -euo pipefail

passed=0
dry_run=0
for arg in "$@"; do
  case "$arg" in
    --founder-passed) passed=1 ;;
    --dry-run) dry_run=1 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done
if [[ "$passed" -ne 1 ]]; then
  echo "A beta tag needs a clean founder test pass. Re-run with --founder-passed once it has one." >&2
  exit 1
fi

branch=$(git rev-parse --abbrev-ref HEAD)
if [[ "$branch" != "classic" ]]; then
  echo "Beta releases come from the classic lane; this checkout is on '$branch'." >&2
  exit 1
fi
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Commit and ship your changes first." >&2
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

net fetch -q "$url" '+refs/heads/classic:refs/remotes/origin/classic' '+refs/tags/*:refs/tags/*'
if [[ "$(git rev-parse HEAD)" != "$(git rev-parse refs/remotes/origin/classic)" ]]; then
  echo "This classic is not what GitHub has. Run scripts/ship-lane.sh first, so the tag is a shipped commit." >&2
  exit 1
fi

day=$(date +%Y%m%d)
n=1
while git rev-parse -q --verify "refs/tags/beta-$day-$n" >/dev/null; do
  n=$((n + 1))
done
tag="beta-$day-$n"
commit=$(git rev-parse --short HEAD)

scripts_dir=$(dirname "${BASH_SOURCE[0]}")
allow_unsigned="${VIBECUT_ALLOW_UNSIGNED:-0}"
if [[ "$allow_unsigned" != "1" ]]; then
  # A fixed commit, not a merge-base with main: main moves with Studio, and if
  # it were rewritten or went missing the range would widen to all history.
  base="${VIBECUT_RELEASE_SIGN_BASE:-$(sed -n '/^[0-9a-f]/{p;q;}' "$scripts_dir/release-signature-base" 2>/dev/null || true)}"
  if [[ -z "$base" ]] || ! git merge-base --is-ancestor "$base" HEAD 2>/dev/null; then
    echo "The signature base '${base:-none}' is not behind this classic. Restore scripts/release-signature-base. Nothing was tagged." >&2
    exit 1
  fi
  range="$base..HEAD"
  if ! "$scripts_dir/verify-signatures.sh" --range "$range"; then
    echo "Unsigned commits in the release range. Sign them before tagging. The pre-signing 732254a and 8186e2a are recorded exceptions." >&2
    exit 1
  fi
fi

if [[ "$dry_run" -eq 1 ]]; then
  echo "Would tag $commit as $tag and push it."
  exit 0
fi
if [[ "$allow_unsigned" == "1" ]]; then
  git tag -a "$tag" -m "Beta $tag: classic at $commit. Build with VIBECUT_EDITION=classic and no VIBECUT_FEATURES."
else
  git tag -s "$tag" -m "Beta $tag: classic at $commit. Build with VIBECUT_EDITION=classic and no VIBECUT_FEATURES."
  if ! "$scripts_dir/verify-signatures.sh" --tag "$tag"; then
    echo "Tag $tag is not signed. Nothing was pushed." >&2
    exit 1
  fi
fi
net push "$url" "refs/tags/$tag"
echo "Released $tag ($commit). Testers build from this tag, not from the branch."
