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
