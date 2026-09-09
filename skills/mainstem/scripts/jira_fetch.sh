#!/usr/bin/env bash
# Refresh jira.json with plain curl against the Jira REST API — no model, no MCP.
# Token: macOS keychain item (service ms-jira-token, account = Jira email), or ~/.config/mainstem/jira_token.
# Create a token at https://id.atlassian.com/manage-profile/security/api-tokens and store it with:
#   security add-generic-password -a <your-jira-email> -s ms-jira-token -w '<token>' -U
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG() { python3 "$HERE/config.py" get "$1"; }

JIRA_HOST="$(CFG jira.host)"
if [ -z "$JIRA_HOST" ]; then
  echo "jira: no jira.host configured, skipping" >&2
  exit 0
fi
SITE="https://$JIRA_HOST"
EMAIL="${JIRA_EMAIL:-$(CFG jira.email 2>/dev/null || true)}"
OUT="${1:-$(python3 "$HERE/config.py" path dataDir)}"
TOKEN=$(security find-generic-password -a "$EMAIL" -s ms-jira-token -w 2>/dev/null || cat "$HOME/.config/mainstem/jira_token" 2>/dev/null || true)
if [ -z "$TOKEN" ]; then
  echo "jira_fetch: no token (keychain ms-jira-token or ~/.config/mainstem/jira_token) — jira.json left as is" >&2
  exit 3
fi
PROJECTS_JSON="$(CFG jira.projects)"
JQL='assignee = currentUser() AND statusCategory != Done'
PROJECT_FILTER=$(python3 -c '
import json, sys
projects = json.loads(sys.argv[1]) if sys.argv[1] else []
print(" AND project in (" + ",".join(projects) + ")" if projects else "")
' "$PROJECTS_JSON")
JQL="${JQL}${PROJECT_FILTER} ORDER BY priority ASC, updated DESC"
RAW=$(mktemp "${TMPDIR:-/tmp}/ms-jira.XXXXXX"); trap 'rm -f "$RAW"' EXIT
code=$(curl -sS -o "$RAW" -w '%{http_code}' -u "$EMAIL:$TOKEN" -G "$SITE/rest/api/3/search/jql" \
  --data-urlencode "jql=$JQL" --data-urlencode "fields=summary,status,priority,issuetype,updated,project,duedate,labels" \
  --data-urlencode "maxResults=100")
[ "$code" = 200 ] || { echo "jira_fetch: HTTP $code: $(head -c 300 "$RAW")" >&2; exit 4; }
python3 - "$RAW" "$OUT" <<'PY'
import json, sys, datetime
raw, out = sys.argv[1], sys.argv[2]
issues = json.load(open(raw)).get("issues", [])
def f(i, k): return (i.get("fields") or {}).get(k)
rows = [{
    "key": i["key"], "summary": f(i, "summary"),
    "status": (f(i, "status") or {}).get("name"),
    "priority": (f(i, "priority") or {}).get("name"),
    "type": (f(i, "issuetype") or {}).get("name"),
    "updated": f(i, "updated"), "project": (f(i, "project") or {}).get("key"),
    "due": f(i, "duedate"), "labels": f(i, "labels") or None,
} for i in issues]
json.dump(rows, open(f"{out}/jira.json", "w"), indent=1)
open(f"{out}/jira_baked_at.txt", "w").write(datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
print(f"jira: {len(rows)} open issues")
PY
