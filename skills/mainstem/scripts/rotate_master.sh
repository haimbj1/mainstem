#!/usr/bin/env bash
# Respawn the master's tmux pane in place: old master dies, a fresh claude boots and runs the ritual.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG() { python3 "$HERE/config.py" get "$1"; }
CFGPATH() { python3 "$HERE/config.py" path "$1"; }

SESSION="$(CFG masterTmuxSession)"
SB="$(CFGPATH dataDir)"
HOST="$(CFG host)"
PORT="$(CFG port)"
MODEL="${MS_MASTER_MODEL:-claude-fable-5}"
TMUX_BIN="${TMUX_BIN:-$(command -v tmux 2>/dev/null || echo /opt/homebrew/bin/tmux)}"
# The server's launchd PATH has no ~/.local/bin — a bare `claude` makes the pane die instantly.
CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude 2>/dev/null || echo "$HOME/.local/bin/claude")}"
if ! "$TMUX_BIN" has-session -t "$SESSION" 2>/dev/null; then
  echo "rotate: no '$SESSION' tmux session — start it with ms_master.sh first" >&2
  exit 3
fi
python3 - "$SB/requests.json" <<'PY'
import json,sys
p=sys.argv[1]; r=json.load(open(p)); lst=r if isinstance(r,list) else r.get("requests",[])
for q in lst:
    if q.get("kind")=="rotate" and q.get("status") in ("pending","working"):
        q["status"]="done"; q["reply"]="Rotating the master session now — fresh context, same tab."
json.dump(r,open(p,"w"),indent=1)
PY
RITUAL="You are the rotated MainStem master. Invoke the mainstem skill and follow its 'New master — start ritual': read the configured masterHandoffNote path, TaskList to confirm no Monitor is already running, arm the requests.json Monitor, curl -s $HOST:$PORT/health. Then wait. Do not refresh or message other sessions."
"$TMUX_BIN" respawn-pane -k -t "${SESSION}:0.0" "$CLAUDE_BIN --model $MODEL $(printf %q "$RITUAL")"
sleep 1
if ! "$TMUX_BIN" has-session -t "$SESSION" 2>/dev/null; then
  echo "rotate: pane died right after respawn — claude did not start ($CLAUDE_BIN)" >&2
  exit 4
fi
echo "rotate: respawned ${SESSION}:0.0"
