#!/usr/bin/env bash
# Headless render check that never touches the user's Chrome profile or keychain.
# usage: render_check.sh <html-file> [screenshot.png] [WxH]
set -euo pipefail
HTML=$(cd "$(dirname "${1:?html file}")" && pwd)/$(basename "$1")
SHOT=${2:-}
SIZE=${3:-1440,1200}
CH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
# Never run while the user's own Chrome is open: a second instance of the same binary has crashed it.
if pgrep -f "Google Chrome.app/Contents/MacOS/Google Chrome" | xargs -I{} ps -o args= -p {} 2>/dev/null | grep -v -- '--headless' | grep -q .; then
  echo "render_check: user's Chrome is running — skipping the headless render (use the node syntax check instead)" >&2
  exit 0
fi
PROFILE=$(mktemp -d "${TMPDIR:-/tmp}/ms-chrome.XXXXXX")
ERR=$(mktemp "${TMPDIR:-/tmp}/ms-chrome-err.XXXXXX")
cleanup() { rm -rf "$PROFILE" "$ERR"; }
trap cleanup EXIT
COMMON=(--headless=new --disable-gpu --no-sandbox --no-first-run --no-default-browser-check
        "--user-data-dir=$PROFILE" --use-mock-keychain --password-store=basic
        --disable-sync --disable-background-networking --disable-component-update --disable-remote-fonts --disable-extensions
        --virtual-time-budget=3000)
"$CH" "${COMMON[@]}" --enable-logging=stderr --dump-dom "file://$HTML" 2>"$ERR" \
  | grep -o 'id="s-queue"\|id="s-reviews"\|class="dec' | sort | uniq -c || true
errs=$(grep -ciE 'uncaught|TypeError|ReferenceError|SyntaxError' "$ERR" || true)
echo "js-errors: ${errs:-0}"
if [ -n "$SHOT" ]; then
  "$CH" "${COMMON[@]}" "--window-size=$SIZE" "--screenshot=$SHOT" "file://$HTML" 2>/dev/null
  echo "screenshot: $SHOT"
fi
