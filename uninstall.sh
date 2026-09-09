#!/usr/bin/env bash
set -euo pipefail
if [ "$(uname -s)" = "Darwin" ]; then
  LABEL="io.mainstem.server"
  launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 && echo "stopped" || echo "was not loaded"
else
  systemctl --user disable --now mainstem.service >/dev/null 2>&1 && echo "stopped" \
    || echo "was not loaded"
fi
rm -f "$HOME/.claude/skills/mainstem" "$HOME"/.claude/agents/ms-*.md
echo "symlinks removed — config and data left untouched"
