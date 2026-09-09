#!/usr/bin/env bash
# Launch (or attach) the master in a dedicated tmux session (configured masterTmuxSession).
# Rotation respawns THIS pane in place, so the master always lives in the same iTerm tab.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG() { python3 "$HERE/config.py" get "$1"; }
CFGPATH() { python3 "$HERE/config.py" path "$1"; }

SESSION="$(CFG masterTmuxSession)"
WORKROOT="$(CFGPATH workRoot)"
HOST="$(CFG host)"
PORT="$(CFG port)"
MODEL="${MS_MASTER_MODEL:-claude-fable-5}"
TMUX_BIN="${TMUX_BIN:-$(command -v tmux 2>/dev/null || echo /opt/homebrew/bin/tmux)}"
# The server's launchd PATH has no ~/.local/bin — a bare `claude` makes the pane die instantly.
CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude 2>/dev/null || echo "$HOME/.local/bin/claude")}"
RITUAL="You are the MainStem master session. Invoke the mainstem skill and follow its 'New master — start ritual': read the configured masterHandoffNote path, run TaskList to confirm no MainStem Monitor is already running, then arm the requests.json Monitor, then curl -s $HOST:$PORT/health. Then wait for requests. Do not refresh, re-read old requests, or message other sessions."
if ! "$TMUX_BIN" has-session -t "$SESSION" 2>/dev/null; then
  "$TMUX_BIN" new-session -d -s "$SESSION" -c "$WORKROOT" "$CLAUDE_BIN --model $MODEL $(printf %q "$RITUAL")"
  sleep 1
  if ! "$TMUX_BIN" has-session -t "$SESSION" 2>/dev/null; then
    echo "ms_master: '$SESSION' died right after launch — claude did not start ($CLAUDE_BIN)" >&2
    exit 4
  fi
fi
if [ -z "${TMUX:-}" ]; then
  osascript <<OSA 2>/dev/null || echo "tmux session '$SESSION' ready — attach with: $TMUX_BIN attach -t $SESSION"
tell application "iTerm2"
  tell current window to create tab with default profile
  tell current session of current window to write text "$TMUX_BIN attach -t $SESSION"
end tell
OSA
fi
