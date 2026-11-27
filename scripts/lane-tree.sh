#!/bin/sh
# Main PO only. Emit the candidate tree ID; leave HEAD, refs and the real index alone.
set -eu
if [ "$#" -lt 2 ]; then
    echo 'usage: lane-tree.sh BASE_COMMIT OWNED_FILE ...' >&2
    exit 2
fi
base=$(git rev-parse --verify "$1^{commit}")
shift
if [ "$(git rev-parse --show-prefix)" != "" ]; then
    echo 'run from the repository root' >&2
    exit 2
fi
tmp=$(mktemp -d)
trap 'rm -f "$tmp/index" "$tmp/index.lock"; rmdir "$tmp"' EXIT
export GIT_INDEX_FILE="$tmp/index" GIT_LITERAL_PATHSPECS=1
git read-tree "$base"
for path do
    case "/$path/" in
        *//*|*/../*|*/./*|*/.git/*) echo "invalid path: $path" >&2; exit 2 ;;
    esac
    if [ -d "$path" ] || [ "$(git cat-file -t "$base:$path" 2>/dev/null || true)" = tree ]; then
        echo "reserve individual files: $path" >&2
        exit 2
    fi
done
git add -A -- "$@"
# A file replacing a parent directory can otherwise stage an implicit deletion.
git diff --cached --no-renames --name-only -z "$base" |
    python3 -c '
import os
import sys

owned = {os.fsencode(path) for path in sys.argv[1:]}
changed = set(sys.stdin.buffer.read().split(b"\0")) - {b""}
if changed - owned:
    sys.exit("candidate changes a path outside the reservation")
' "$@"
git diff --cached --check "$base"
if git diff --cached --quiet "$base"; then
    echo 'candidate has no changes' >&2
    exit 1
fi
git write-tree
