#!/usr/bin/env bash
# Run the Claude Jump logic directly via osascript (no URL-scheme app, no Automation prompt for a new app).
# usage: jump.sh "ms://session?...|ms://start?..."
set -euo pipefail
if [ "$(uname -s)" != "Darwin" ]; then
  echo "refused: jump requires macOS (iTerm2 + AppleScript) — not available on this platform" >&2
  exit 1
fi
URL="${1:?mc url}"
case "$URL" in
  ms://*) ;;
  *) echo "refused: not a ms:// url" >&2; exit 1 ;;
esac
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/claude-jump.applescript"
TMP=$(mktemp "${TMPDIR:-/tmp}/msjump.XXXXXX.applescript")
trap 'rm -f "$TMP"' EXIT
sed 's/on open location theURL/on jump(theURL)/; s/end open location/end jump/' "$SRC" > "$TMP"
# Escape backslash then double-quote so a `"` in the URL (e.g. a jump prompt with quoted text)
# cannot break out of the AppleScript string literal we are about to write.
ESCAPED=$(printf '%s' "$URL" | sed 's/\\/\\\\/g; s/"/\\"/g')
printf 'jump("%s")\n' "$ESCAPED" >> "$TMP"
osascript "$TMP"
