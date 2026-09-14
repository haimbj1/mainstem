#!/usr/bin/env bash
set -euo pipefail
if [ "$(uname -s)" = "Darwin" ]; then
  LABEL="io.mainstem.server"
  launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 && echo "stopped" || echo "was not loaded"
  launchctl bootout "gui/$(id -u)/io.mainstem.bake" >/dev/null 2>&1 || true
  rm -f "$HOME/Library/LaunchAgents/io.mainstem.bake.plist"
else
  systemctl --user disable --now mainstem.service >/dev/null 2>&1 && echo "stopped" \
    || echo "was not loaded"
  systemctl --user disable --now mainstem-bake.timer >/dev/null 2>&1 || true
  rm -f "$HOME/.config/systemd/user/mainstem-bake.service" "$HOME/.config/systemd/user/mainstem-bake.timer"
fi
rm -f "$HOME/.claude/skills/mainstem" "$HOME"/.claude/agents/ms-*.md
echo "symlinks removed — config and data left untouched"
