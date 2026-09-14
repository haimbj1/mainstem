#!/usr/bin/env bash
# Preview a branch of the board before merging it, on its own port, against a
# SNAPSHOT copy of your real data. The live service and its data stay untouched.
#
#   preview.sh <branch-or-pr-ref> [port]     (default port 7797; Ctrl-C cleans up)
#
# Caution: the preview is a full server. Its page write-buttons (jump, push, restore)
# act on this machine for real. Look, do not click, unless you mean it.
set -euo pipefail
BRANCH=${1:?usage: preview.sh <branch> [port]}
PORT=${2:-7797}
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"

WT="$(mktemp -d "${TMPDIR:-/tmp}/ms-preview-wt.XXXXXX")"
DATA="$(mktemp -d "${TMPDIR:-/tmp}/ms-preview-data.XXXXXX")"
cleanup() {
  git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1 || true
  rm -rf "$DATA"
}
trap cleanup EXIT

git -C "$REPO" fetch -q origin "$BRANCH" 2>/dev/null || true
git -C "$REPO" worktree add -q "$WT" "$BRANCH"

SRC="$(python3 "$HERE/config.py" path dataDir)"
cp "$SRC"/*.json "$DATA"/ 2>/dev/null || true
cp "$SRC"/collected_at.txt "$DATA"/ 2>/dev/null || true

# real config, with only port + dataDir swapped for the preview
python3 - "$DATA" "$PORT" <<PY > "$DATA/preview-config.json"
import json, sys
sys.path.insert(0, "$HERE")
from config import load_config
c = load_config()
c["dataDir"], c["port"] = sys.argv[1], int(sys.argv[2])
json.dump(c, sys.stdout, indent=1)
PY

echo "preview: branch $BRANCH on http://127.0.0.1:$PORT (data snapshot: $DATA)"
echo "preview: Ctrl-C stops it and removes the worktree + snapshot"
MS_CONFIG="$DATA/preview-config.json" exec python3 "$WT/skills/mainstem/scripts/ms_server.py"
