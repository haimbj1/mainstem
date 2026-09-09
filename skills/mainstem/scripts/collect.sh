#!/usr/bin/env bash
# Collect local + GitHub data for mainstem into $dataDir/*.json
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG() { python3 "$HERE/config.py" get "$1"; }
CFGPATH() { python3 "$HERE/config.py" path "$1"; }

OUT="$(CFGPATH dataDir)"
WORK="$(CFGPATH workRoot)"
SESSDIR="$(CFGPATH sessionNotesDir)"
GH_LOGIN="$(CFG github.login)"
if [ -z "$GH_LOGIN" ]; then
  GH_LOGIN="$(gh api user -q .login)"
fi
mkdir -p "$OUT"

# One panel can be refreshed on its own: the board's per-panel button pays only for
# what it shows, instead of a full gh + git sweep.
PANEL=${1:-all}
case "$PANEL" in
  all|worktrees|sessions|prs|reviews|jira) ;;
  *) echo "unknown panel: $PANEL (all|worktrees|sessions|prs|reviews|jira)" >&2; exit 2;;
esac
want(){ [ "$PANEL" = all ] || [ "$PANEL" = "$1" ]; }

# --- worktrees ---------------------------------------------------------------
if want worktrees; then
{
  echo '['
  first=1
  for d in "$WORK"/*/; do
    d=${d%/}
    [ -e "$d/.git" ] || continue
    name=$(basename "$d")
    remote=$(git -C "$d" remote get-url origin 2>/dev/null | sed -E 's#.*github.com[:/]##; s#\.git$##' || true)
    br=$(git -C "$d" branch --show-current 2>/dev/null || true)
    dirty=$(git -C "$d" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    behind=""; ahead=""
    if ab=$(git -C "$d" rev-list --left-right --count '@{u}...HEAD' 2>/dev/null); then
      behind=${ab%%	*}; ahead=${ab##*	}
    fi
    last_rel=$(git -C "$d" log -1 --format='%cr' 2>/dev/null || true)
    last_iso=$(git -C "$d" log -1 --format='%cI' 2>/dev/null || true)
    last_msg=$(git -C "$d" log -1 --format='%s' 2>/dev/null || true)
    if [ -f "$d/.git" ]; then kind=worktree; main=$(dirname "$(git -C "$d" rev-parse --git-common-dir)"); else kind=clone; main=""; fi
    [ $first = 1 ] || echo ','
    first=0
    jq -nc --arg name "$name" --arg path "$d" --arg remote "$remote" --arg branch "$br" \
      --argjson dirty "${dirty:-0}" --arg behind "$behind" --arg ahead "$ahead" \
      --arg last_rel "$last_rel" --arg last_iso "$last_iso" --arg last_msg "$last_msg" --arg kind "$kind" --arg main "$main" \
      '{name:$name,path:$path,remote:$remote,branch:$branch,dirty:$dirty,kind:$kind,main:$main,
        behind:(if $behind=="" then null else ($behind|tonumber) end),
        ahead:(if $ahead=="" then null else ($ahead|tonumber) end),
        last_rel:$last_rel,last_iso:$last_iso,last_msg:$last_msg}'
  done
  echo ']'
} > "$OUT/worktrees.json"
fi

# --- live sessions (registry) -------------------------------------------------
if want sessions; then
jq -s '[.[] | select(.kind=="interactive" or .kind=="bg") | {pid,name,cwd,status,procStart,startedAt,version,sessionId,tmux}]' \
  "$SESSDIR"/*.json > "$OUT/sessions.raw.json" 2>/dev/null || echo '[]' > "$OUT/sessions.raw.json"
# attach the controlling tty so the ms:// handler can find the exact iTerm tab
python3 - "$OUT" <<'PY'
import json, re, subprocess, sys, os
out = sys.argv[1]; sess = json.load(open(f"{out}/sessions.raw.json"))
def chain(pid):
    # claude runs on its own pty; the iTerm tab owns an ancestor's tty — collect the whole chain.
    # A session hosted by an editor (Zed ACP, VS Code) has no tty at all; name the host so the page
    # does not offer an iTerm jump that cannot work.
    ttys, seen, host = [], 0, ""
    while pid and pid > 1 and seen < 8:
        r = subprocess.run(["ps", "-o", "tty=,ppid=,comm=", "-p", str(pid)], capture_output=True, text=True).stdout.split(None, 2)
        if len(r) < 2: break
        comm = r[2] if len(r) > 2 else ""
        if "/Zed" in comm or "zed" in comm.lower().split("/")[-1]: host = "zed"
        elif "Visual Studio Code" in comm or "Code Helper" in comm: host = "vscode"
        if r[0] != "??" and f"/dev/{r[0]}" not in ttys: ttys.append(f"/dev/{r[0]}")
        pid, seen = int(r[1]), seen + 1
    return ",".join(ttys), host

def session_kind_env(pid):
    # A launcher can export MS_SESSION_KIND before starting claude so a headless session (no tty
    # to inspect) still classifies correctly. /proc/<pid>/environ is readable same-uid on Linux;
    # macOS hides another process's environment from ps unless the reader is root, so this is
    # best-effort there and normally falls through to the name/tty rule below.
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            for kv in f.read().split(b"\0"):
                if kv.startswith(b"MS_SESSION_KIND="):
                    return kv.split(b"=", 1)[1].decode()
    except OSError:
        pass
    try:
        ps_env = subprocess.run(["ps", "eww", "-p", str(pid)], capture_output=True, text=True).stdout
        m = re.search(r"MS_SESSION_KIND=(\S*)", ps_env)
        if m: return m.group(1)
    except Exception:
        pass
    return ""

AGENT_NAMES = {"ms-executor", "ms-quickwins", "ms-refresher", "ms-reviewer"}

def classify_kind(name, tty, host, tmux, env_kind):
    if env_kind in ("interactive", "background", "agent"):
        return env_kind
    if name in AGENT_NAMES:
        return "agent"
    if tty or host:
        return "interactive"
    return "background"

for s in sess:
    try: s["tty"], s["host"] = chain(s["pid"])
    except Exception: s["tty"], s["host"] = "", ""
    s["kind"] = classify_kind(s.get("name", ""), s["tty"], s["host"], s.get("tmux"), session_kind_env(s["pid"]))
json.dump(sess, open(f"{out}/sessions.json", "w"))
os.remove(f"{out}/sessions.raw.json")
PY

# --- session status notes ($sessionNotesDir/*.md) -----------------------------
{
  echo '['
  first=1
  for f in "$SESSDIR"/*.md; do
    [ -e "$f" ] || continue
    [ $first = 1 ] || echo ','
    first=0
    # portable mtime (BSD `stat -f` and GNU `stat -c` disagree on flags/format;
    # python3's stdlib gives the same ISO-with-offset string on both).
    mtime=$(python3 -c "import datetime,os,sys; print(datetime.datetime.fromtimestamp(os.path.getmtime(sys.argv[1])).astimezone().strftime('%Y-%m-%dT%H:%M:%S%z'))" "$f")
    jq -nc --arg file "$(basename "$f")" --arg mtime "$mtime" --rawfile body "$f" \
      '{file:$file,mtime:$mtime,head:($body[:1400])}'
  done
  echo ']'
} > "$OUT/session_notes.json"
fi

# --- GitHub -------------------------------------------------------------------
if want prs; then
# write-then-move: a failed gh must never truncate the live file the page reads
gh api graphql -f query='query{ viewer{ login pullRequests(first:50,states:OPEN,orderBy:{field:UPDATED_AT,direction:DESC}){ nodes{ number title url isDraft updatedAt createdAt headRefName baseRefName additions deletions reviewDecision mergeable repository{nameWithOwner} commits(last:1){nodes{commit{statusCheckRollup{state}}}} reviews(last:20){nodes{state author{login}}} comments{totalCount} } } } }' \
  > "$OUT/my_prs.json.tmp" && mv "$OUT/my_prs.json.tmp" "$OUT/my_prs.json"
fi
if want reviews; then
# review requests, split into direct (me as reviewer) vs team — team ones are noise for the queue.
# A third tier, "watch" (config reviews.watchRepos), surfaces open PRs in repos/orgs the developer
# only watches — no formal ask there, so a direct/team row for the same PR always wins over it.
direct_and_team_json="$(gh api graphql -f query='query{ search(query:"is:pr is:open review-requested:'"$GH_LOGIN"'", type:ISSUE, first:50){ nodes{ ... on PullRequest{ number title url isDraft updatedAt createdAt headRefName baseRefName author{login} repository{nameWithOwner} myReviews: reviews(author:"'"$GH_LOGIN"'", last:1){nodes{state}} reviewRequests(first:10){nodes{requestedReviewer{ __typename ... on User{login} ... on Team{name} }}} } } } }' \
  | jq --arg me "$GH_LOGIN" '[.data.search.nodes[] | {number,title,url,isDraft,updatedAt,createdAt,headRefName,baseRefName,my_review:(.myReviews.nodes[0].state // null),author:{login:.author.login},repository:{nameWithOwner:.repository.nameWithOwner}, direct: ([.reviewRequests.nodes[].requestedReviewer | select(.__typename=="User" and .login==$me)] | length > 0), teams: [.reviewRequests.nodes[].requestedReviewer | select(.__typename=="Team") | .name]}]')"

watch_prs='[]'
WATCH_REPOS="$(CFG reviews.watchRepos)"
if [ -n "$WATCH_REPOS" ] && [ "$WATCH_REPOS" != "[]" ]; then
  watch_prs="$(echo "$WATCH_REPOS" | python3 -c '
import json, sys
for entry in json.load(sys.stdin):
    print(entry)
' | while read -r entry; do
      # one malformed entry must not abort the whole collection (set -e + pipefail otherwise
      # take down every other watch repo with it) -- validate the shape, and fall back to
      # empty on a gh/jq failure instead of letting the pipeline non-zero exit propagate
      if [[ ! "$entry" =~ ^[A-Za-z0-9_.-]+/([A-Za-z0-9_.-]+|\*)$ ]]; then
        echo "reviews.watchRepos: skipping malformed entry: $entry" >&2
        continue
      fi
      if [[ "$entry" == */\* ]]; then q="is:pr is:open org:${entry%/*}"; else q="is:pr is:open repo:$entry"; fi
      gh api graphql -f query='query{ search(query:"'"$q"'", type:ISSUE, first:50){ nodes{ ... on PullRequest{ number title url isDraft updatedAt createdAt headRefName baseRefName author{login} repository{nameWithOwner} myReviews: reviews(author:"'"$GH_LOGIN"'", last:1){nodes{state}} } } } }' \
        | jq '[.data.search.nodes[] | {number,title,url,isDraft,updatedAt,createdAt,headRefName,baseRefName,my_review:(.myReviews.nodes[0].state // null),author:{login:.author.login},repository:{nameWithOwner:.repository.nameWithOwner}, direct:false, teams:[]}]' \
        || { echo "reviews.watchRepos: gh/jq failed for entry $entry — skipping" >&2; echo '[]'; }
    done | jq -s 'add // []')"
fi

# Merge: direct/team rows keep their provenance; a watch row is dropped if the same PR url already
# has a direct/team row (a formal ask always outranks merely watching the repo); own-authored PRs
# are excluded everywhere — "My PRs" is the panel for those, not the review queue.
jq -n --argjson known "$direct_and_team_json" --argjson watch "$watch_prs" --arg me "$GH_LOGIN" '
  ($known | map(.provenance = (if .direct then "direct" else "team" end))) as $known_p
  | ($known_p | map(.url)) as $known_urls
  | ($watch | map(select(.url as $u | ($known_urls | index($u)) == null)) | map(.provenance = "watch")) as $watched_only
  | ($known_p + $watched_only) | map(select(.author.login != $me))
' > "$OUT/review_requests.json"
fi


# --- jira (curl, no model) ------------------------------------------------------
if want jira; then
  if [ "$(CFG modules.jira)" = "true" ]; then
    if [ "$PANEL" = jira ]; then bash "$HERE/jira_fetch.sh" "$OUT"
    else bash "$HERE/jira_fetch.sh" "$OUT" || echo "jira: skipped (see above)" >&2; fi
  else
    echo "jira: not configured (modules.jira is false)" >&2
  fi
fi
date -u +%Y-%m-%dT%H:%M:%SZ > "$OUT/collected_at.txt"
count(){ jq "$2" "$OUT/$1" 2>/dev/null || echo '?'; }
echo "collected ($PANEL): $(count worktrees.json length) worktrees, $(count sessions.json length) sessions, $(count my_prs.json '.data.viewer.pullRequests.nodes|length') my PRs, $(count review_requests.json length) review requests"
