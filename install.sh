#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$HERE/skills/mainstem/scripts"

if ! bash "$SCRIPTS/ms_doctor.sh"; then
  echo "one or more required tools are missing — see above. Install them, then re-run install.sh." >&2
  exit 1
fi

CFG() { python3 "$SCRIPTS/config.py" get "$1"; }
CFGPATH() { python3 "$SCRIPTS/config.py" path "$1"; }

PORT="$(CFG port)"
DATA_DIR="$(CFGPATH dataDir)"
mkdir -p "$DATA_DIR"
# Rendered into every service template's PATH: services must see the user's own bin
# (claude lives there), and templates may not carry literal home paths.
USER_LOCAL_BIN="$HOME/.local/bin"

# Symlink skill + agents into Claude Code's user dirs (standalone install; plugin install skips this).
mkdir -p "$HOME/.claude/skills" "$HOME/.claude/agents"
ln -sfn "$HERE/skills/mainstem" "$HOME/.claude/skills/mainstem"
for a in "$HERE"/agents/ms-*.md; do
  ln -sfn "$a" "$HOME/.claude/agents/$(basename "$a")"
done

MS_CONFIG_PATH="${MS_CONFIG:-$HOME/.config/mainstem/config.json}"
if [ ! -f "$MS_CONFIG_PATH" ]; then
  mkdir -p "$(dirname "$MS_CONFIG_PATH")"
  cp "$HERE/config.example.json" "$MS_CONFIG_PATH"
  echo "wrote default config to $MS_CONFIG_PATH — edit it, or run the setup conversation"
fi

# A foreign listener on our port makes the service crash-loop while the post-start health
# check happily gets 200 from the OTHER server — refuse early, name the holder.
if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  holder_pid=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN | awk 'NR==2{print $2}')
  holder_cmd=$(ps -o command= -p "$holder_pid" 2>/dev/null || true)
  case "$holder_cmd" in
    *ms_server.py*) : ;;  # our own service holds it — a reinstall replaces it anyway
    *)
      holder=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN | awk 'NR==2{print $1" (pid "$2")"}')
      echo "port $PORT is already in use by $holder — edit \"port\" in $MS_CONFIG_PATH and rerun." >&2
      exit 1;;
  esac
fi

if [ "$(uname -s)" = "Darwin" ]; then
  LABEL="io.mainstem.server"
  PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
  sed -e "s|{{LABEL}}|$LABEL|" -e "s|{{PYTHON_BIN}}|$(command -v python3)|" \
      -e "s|{{REPO_DIR}}|$HERE|" -e "s|{{DATA_DIR}}|$DATA_DIR|" \
      -e "s|{{MS_CONFIG_PATH}}|$MS_CONFIG_PATH|" -e "s|{{USER_LOCAL_BIN}}|$USER_LOCAL_BIN|" \
      "$HERE/service/io.mainstem.plist.template" > "$PLIST"
  launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
  # bootout is asynchronous — an immediate bootstrap races it and fails with I/O error 5
  for i in 1 2 3 4 5; do
    launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null && break
    [ "$i" = 5 ] && { echo "launchctl bootstrap kept failing — try: launchctl bootstrap gui/$(id -u) $PLIST" >&2; exit 1; }
    sleep 1
  done
  launchctl kickstart -k "gui/$(id -u)/$LABEL"
else
  mkdir -p "$HOME/.config/systemd/user"
  UNIT="$HOME/.config/systemd/user/mainstem.service"
  sed -e "s|{{PYTHON_BIN}}|$(command -v python3)|" -e "s|{{REPO_DIR}}|$HERE|" \
      -e "s|{{DATA_DIR}}|$DATA_DIR|" -e "s|{{MS_CONFIG_PATH}}|$MS_CONFIG_PATH|" \
      -e "s|{{USER_LOCAL_BIN}}|$USER_LOCAL_BIN|" \
      "$HERE/service/mainstem.service.template" > "$UNIT"
  systemctl --user daemon-reload
  systemctl --user enable --now mainstem.service
fi

# Daily tokenless bake (bake.sh at 08:30) — installed only when the config opts in.
if [ "$(CFG bake.scheduledDaily)" = "true" ]; then
  if [ "$(uname -s)" = "Darwin" ]; then
    BAKE_LABEL="io.mainstem.bake"
    BAKE_PLIST="$HOME/Library/LaunchAgents/$BAKE_LABEL.plist"
    sed -e "s|{{LABEL}}|$BAKE_LABEL|" -e "s|{{REPO_DIR}}|$HERE|" -e "s|{{DATA_DIR}}|$DATA_DIR|" \
        -e "s|{{MS_CONFIG_PATH}}|$MS_CONFIG_PATH|" -e "s|{{USER_LOCAL_BIN}}|$USER_LOCAL_BIN|" \
        "$HERE/service/io.mainstem.bake.plist.template" > "$BAKE_PLIST"
    launchctl bootout "gui/$(id -u)/$BAKE_LABEL" >/dev/null 2>&1 || true
    # bootout is asynchronous — an immediate bootstrap races it and fails with I/O error 5
    for i in 1 2 3 4 5; do
      launchctl bootstrap "gui/$(id -u)" "$BAKE_PLIST" 2>/dev/null && break
      [ "$i" = 5 ] && { echo "launchctl bootstrap kept failing for the bake job — try: launchctl bootstrap gui/$(id -u) $BAKE_PLIST" >&2; exit 1; }
      sleep 1
    done
    echo "daily bake scheduled: launchd $BAKE_LABEL, 08:30"
  else
    mkdir -p "$HOME/.config/systemd/user"
    sed -e "s|{{REPO_DIR}}|$HERE|" -e "s|{{DATA_DIR}}|$DATA_DIR|" \
        -e "s|{{MS_CONFIG_PATH}}|$MS_CONFIG_PATH|" -e "s|{{USER_LOCAL_BIN}}|$USER_LOCAL_BIN|" \
        "$HERE/service/mainstem-bake.service.template" > "$HOME/.config/systemd/user/mainstem-bake.service"
    cp "$HERE/service/mainstem-bake.timer.template" "$HOME/.config/systemd/user/mainstem-bake.timer"
    systemctl --user daemon-reload
    systemctl --user enable --now mainstem-bake.timer
    echo "daily bake scheduled: systemd mainstem-bake.timer, 08:30"
  fi
fi

for _ in $(seq 1 20); do
  if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    echo "mainstem running at http://127.0.0.1:$PORT"
    echo "open a NEW Claude Code session and type /mainstem — running sessions do not pick up newly installed skills"
    exit 0
  fi
  sleep 0.5
done
echo "server did not come up — check $DATA_DIR/server.log" >&2
exit 1
