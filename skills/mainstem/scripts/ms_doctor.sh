#!/usr/bin/env bash
# Checks for tools mainstem needs. Never installs anything itself — only reports and
# suggests a command. Exit 0 only if every REQUIRED tool is present; missing OPTIONAL tools
# degrade a feature, not the whole install, and don't affect the exit code.
set -uo pipefail
MISSING_REQUIRED=0

check() {
  local name="$1" cmd="$2" required="$3" fix="$4"
  if command -v "$cmd" >/dev/null 2>&1; then
    echo "ok       $name"
  else
    if [ "$required" = "required" ]; then
      echo "MISSING  $name (required) — without it: nothing works. Fix: $fix"
      MISSING_REQUIRED=1
    else
      echo "missing  $name (optional) — without it: a feature degrades gracefully. Fix: $fix"
    fi
  fi
}

check git      git      required "brew install git"
check "GitHub CLI" gh   required "brew install gh && gh auth login"
check jq       jq       required "brew install jq"
check python3  python3  required "brew install python@3.12"
check node     node     required "brew install node"
check tmux     tmux     optional "brew install tmux — without it, no master-session harness"

# claude: warn, never fail. Prefer ~/.local/bin/claude — a bare `command -v` can pick up a
# stale binary from an old install (e.g. in /usr/local/bin).
CLAUDE_BIN="$HOME/.local/bin/claude"
[ -x "$CLAUDE_BIN" ] || CLAUDE_BIN="$(command -v claude 2>/dev/null || true)"
if [ -n "$CLAUDE_BIN" ]; then
  CLAUDE_VER="$("$CLAUDE_BIN" --version 2>/dev/null || true)"
  CLAUDE_MAJOR="$(printf '%s' "$CLAUDE_VER" | grep -oE '[0-9]+' | head -1 || true)"
  if [ -n "$CLAUDE_MAJOR" ] && [ "$CLAUDE_MAJOR" -lt 2 ]; then
    echo "warn     claude is old ($CLAUDE_BIN, ${CLAUDE_VER:-unknown}) — 2.0 or newer expected; update it"
  else
    echo "ok       claude ($CLAUDE_BIN, ${CLAUDE_VER:-version unknown})"
  fi
else
  echo "missing  claude (optional for the server, needed by the master/agents) — install Claude Code"
fi

if [ "$(uname -s)" = "Darwin" ]; then
  if osascript -e 'tell application "iTerm2" to version' >/dev/null 2>&1; then
    echo "ok       iTerm2"
  else
    echo "missing  iTerm2 (optional) — without it: the jump-to-session feature is unavailable"
  fi
fi

if command -v gh >/dev/null 2>&1; then
  if gh auth status >/dev/null 2>&1; then
    echo "ok       gh auth"
  else
    echo "MISSING  gh auth — required for GitHub collection. Fix: gh auth login"
    MISSING_REQUIRED=1
  fi
fi

exit "$MISSING_REQUIRED"
