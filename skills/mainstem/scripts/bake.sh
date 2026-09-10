#!/usr/bin/env bash
# Tokenless daily bake: jira.json (jira_fetch.sh) + calendar.json/gmail.json (google_fetch.py),
# then bake_stamp.json — the freshness stamp the page's staleness banner reads.
# Safe headless: missing credentials skip a source, they never fail the run.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DATA_DIR="$(python3 "$HERE/config.py" path dataDir)"
mkdir -p "$DATA_DIR"

# jira_fetch.sh exits 3 on missing credentials ("left as is") — a skip, not a failure.
jira_rc=0
bash "$HERE/jira_fetch.sh" "$DATA_DIR" || jira_rc=$?
if [ "$jira_rc" != 0 ] && [ "$jira_rc" != 3 ]; then
  echo "bake: jira_fetch.sh failed (rc=$jira_rc) — no stamp written" >&2
  exit "$jira_rc"
fi

# google_fetch.py exits 0 on missing credentials; non-zero only on a real failure.
if ! python3 "$HERE/google_fetch.py"; then
  echo "bake: google_fetch.py failed — no stamp written" >&2
  exit 1
fi

python3 - "$DATA_DIR" <<'PY'
import datetime, json, os, sys
data_dir = sys.argv[1]
path = os.path.join(data_dir, "bake_stamp.json")
tmp = f"{path}.tmp.{os.getpid()}"
when = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
with open(tmp, "w") as f:
    json.dump({"when": when}, f, indent=1)
os.replace(tmp, path)
PY

echo "bake: done — jira rc=$jira_rc · google + stamp written to $DATA_DIR"
