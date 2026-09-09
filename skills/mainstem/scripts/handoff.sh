#!/usr/bin/env bash
# Rewrite the master-session handoff note. Run on retire, on PreCompact, and after big changes.
# Args: [ignored-slot] [note...]  — the note is the ONE line of verbal asks; everything else is read from disk.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG() { python3 "$HERE/config.py" get "$1"; }
CFGPATH() { python3 "$HERE/config.py" path "$1"; }

SB="$(CFGPATH dataDir)"
OUT="$(CFGPATH masterHandoffNote)"
BRAND="$(CFG brand)"
WORKROOT="$(CFGPATH workRoot)"
HOST="$(CFG host)"
PORT="$(CFG port)"
shift || true; NOTE=${*:-}
pend=$(jq -r '([.items[]?,.[]?]|map(select(.status=="pending")))|length' "$SB/pending.json" 2>/dev/null || echo 0)
reqs=$(jq -r '[.[]|select(.status=="pending" or .status=="working")]|length' "$SB/requests.json" 2>/dev/null || echo 0)
master=$(python3 "$HERE/master_usage.py" 2>/dev/null || echo "master context: unknown")
utoday=$(python3 - "$SB/ms_usage.json" <<'PY' 2>/dev/null || echo 0
import json,datetime,os,sys
p=sys.argv[1]
rows=json.load(open(p)) if os.path.exists(p) else []
now=datetime.datetime.now(datetime.timezone.utc)
print(round(sum(r["tokens"] for r in rows if (now-datetime.datetime.fromisoformat(r["when"])).days<1)/1000))
PY
)
{
echo "---"
echo "role: master session ($BRAND) — $WORKROOT"
echo "updated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "mode: local-first (server: the configured launchd job, http://$HOST:$PORT)"
echo "---"
echo "Start ritual (local-first — see SKILL.md § Keep the master small):"
echo "1. read this file; do not redo what it says is done."
echo "2. arm the Monitor on requests.json (command in SKILL.md)."
echo "3. curl -s $HOST:$PORT/health — if down, bash install.sh (repo root)."
echo "4. stop. Do NOT refresh, re-read old requests, message sessions, or re-create any cron."
echo
echo "## Open items (live — these files are the truth, not this note)"
echo "- pending approvals: $pend  ($SB/pending.json)"
echo "- pending/working page requests: $reqs  (python3 pending_requests.py)"
jq -r '([.items[]?,.[]?]|map(select(.status=="pending")))[]|"  - \(.ref) · \(.what) · session \(.session // "-")"' "$SB/pending.json" 2>/dev/null || true
echo
echo "## Awaiting you (verbal, not on the board)"
if [ -n "$NOTE" ]; then echo "- $NOTE"; else echo "- (none recorded)"; fi
echo
echo "## Data age"
echo "- collected_at: $(cat "$SB/collected_at.txt" 2>/dev/null)"
echo "- jira baked: $(cat "$SB/jira_baked_at.txt" 2>/dev/null || echo 'not baked')"
echo "- quickwins: $(jq -r .generated_at "$SB/quickwins.json" 2>/dev/null)"
echo "- reviews indexed: $(jq length "$SB/reviews.json" 2>/dev/null)"
echo "- agent tokens today: ${utoday}k (✦ widget)"
echo "- $master"
} > "$OUT"
echo "handoff → $OUT"
