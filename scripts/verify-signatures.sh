#!/usr/bin/env bash
# Verify the SSH signatures on lane commits and tags.
#
#   scripts/verify-signatures.sh                 # the range this lane ships
#   scripts/verify-signatures.sh --range A..B    # an explicit range
#   scripts/verify-signatures.sh --commit HEAD   # one commit
#   scripts/verify-signatures.sh --tag beta-...  # one tag
#
# Git only checks an SSH signature when gpg.ssh.allowedSignersFile points at a
# file of allowed keys. When that setting is missing, `git verify-commit` fails
# on every commit and `git log --show-signature` says "No signature", even
# though the commit is signed. This script points Git at the tracked
# scripts/allowed_signers itself, so verification does not depend on a global
# Git setting and does not silently pass an unsigned commit.
#
# Environment:
#   VIBECUT_ALLOWED_SIGNERS   use this file instead of the tracked one
#   VIBECUT_SIGN_EXCEPTIONS   space-separated commits recorded as pre-signing
#                             exceptions (default: 732254a 8186e2a)
#
# It never trusts VIBECUT_ALLOW_UNSIGNED; that switch only exists in
# scripts/release.sh for the tagged build and is not a verification result.
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
range=""
commit=""
tag=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --range) range="${2:?--range needs a revision range}"; shift 2 ;;
    --commit) commit="${2:?--commit needs a revision}"; shift 2 ;;
    --tag) tag="${2:?--tag needs a tag name}"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

signers="${VIBECUT_ALLOWED_SIGNERS:-}"
if [[ -z "$signers" ]]; then
  signers="$root/scripts/allowed_signers"
fi
if [[ ! -f "$signers" ]]; then
  echo "No allowed signers file. Set VIBECUT_ALLOWED_SIGNERS or restore scripts/allowed_signers." >&2
  exit 1
fi

git_sig() {
  git -c "gpg.ssh.allowedSignersFile=$signers" "$@"
}

if [[ -n "$tag" ]]; then
  if ! git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    echo "Tag $tag does not exist." >&2
    exit 1
  fi
  if out=$(git_sig verify-tag "$tag" 2>&1); then
    echo "Signed tag: $tag ($(git rev-parse --short "$tag^{commit}"))"
    exit 0
  fi
  echo "Tag $tag is not signed by an allowed key." >&2
  echo "$out" >&2
  exit 1
fi

if [[ -z "$range" ]]; then
  if [[ -n "$commit" ]]; then
    range="$commit"
  else
    branch=$(git rev-parse --abbrev-ref HEAD)
    base=""
    if git rev-parse -q --verify "refs/remotes/origin/$branch" >/dev/null; then
      base=$(git merge-base HEAD "refs/remotes/origin/$branch" 2>/dev/null || true)
    elif git rev-parse -q --verify refs/remotes/origin/main >/dev/null; then
      base=$(git merge-base HEAD refs/remotes/origin/main 2>/dev/null || true)
    fi
    range="${base:+$base..}HEAD"
  fi
fi

if ! commits=$(git rev-list --reverse "$range" 2>/dev/null); then
  echo "Cannot read the range '$range'." >&2
  exit 1
fi
if [[ -z "$commits" ]]; then
  echo "No commits to verify in '$range'."
  exit 0
fi

exceptions=" ${VIBECUT_SIGN_EXCEPTIONS:-732254a 8186e2a} "
signed=0
excepted=0
failed=()

for sha in $commits; do
  short=$(git rev-parse --short "$sha")
  if [[ "$exceptions" == *" $short "* ]]; then
    excepted=$((excepted + 1))
    continue
  fi
  if out=$(git_sig verify-commit "$sha" 2>&1); then
    signed=$((signed + 1))
    continue
  fi
  failed+=("$short $(git log -1 --format=%s "$sha")")
  printf '%s\n' "$out" | sed 's/^/   /' >&2
done

echo "Range: $range"
echo "Signed: $signed · exceptions: $excepted · failed: ${#failed[@]}"

if ((${#failed[@]} > 0)); then
  echo "These commits are not signed by an allowed key:" >&2
  printf '  %s\n' "${failed[@]}" >&2
  echo "Sign them with the configured key before shipping. Do not hide it with VIBECUT_ALLOW_UNSIGNED." >&2
  exit 1
fi
