#!/usr/bin/env python3
"""Track the master session's own context cost in master_usage.json.

Reads the master's transcript (the newest .jsonl under the Claude Code project
directory for the configured workRoot — the master is the one writing right now;
override with MS_MASTER_SESSION=<uuid>), takes the last request's input + cache
tokens as the current context size, and updates {current, history}. A new session
id rolls the previous master into history — that is the per-rotation zeroing.

Run from handoff.sh; safe to run any time. Prints one line for the note.
"""
import datetime
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config  # noqa: E402

CFG = config.load_config()
SB = CFG["dataDir"]
PROJ = os.path.expanduser("~/.claude/projects/" + CFG["workRoot"].replace("/", "-"))
OUT = os.path.join(SB, "master_usage.json")


def transcript_path():
    sid = os.environ.get("MS_MASTER_SESSION")
    if sid:
        return os.path.join(PROJ, sid + ".jsonl")
    files = glob.glob(PROJ + "/*.jsonl")
    if not files:
        sys.exit("no transcripts in " + PROJ)
    return max(files, key=os.path.getmtime)


def context_tokens(path):
    """Context size = the last assistant message's input + cache tokens."""
    last = 0
    with open(path) as fh:
        for line in fh:
            if '"usage"' not in line:
                continue
            try:
                u = (json.loads(line).get("message") or {}).get("usage")
            except json.JSONDecodeError:
                continue
            if u and "input_tokens" in u:
                last = (u.get("input_tokens") or 0) \
                     + (u.get("cache_read_input_tokens") or 0) \
                     + (u.get("cache_creation_input_tokens") or 0)
    return last


def refresh_current():
    """Re-read the KNOWN current master's transcript and update its token count.

    Never guesses which session is the master and never rotates — the session
    pointer only moves when the master itself runs handoff.sh. Safe for the
    server to run on every collect cycle, so the board's master counter stays
    fresh between handoffs. Quiet no-op when there is nothing to refresh.
    """
    if not os.path.exists(OUT):
        return
    d = json.load(open(OUT))
    cur = d.get("current")
    if not cur or not cur.get("session"):
        return
    path = os.path.join(PROJ, cur["session"] + ".jsonl")
    if not os.path.exists(path):
        return
    tokens = context_tokens(path)
    if tokens == cur.get("tokens"):
        return
    cur["tokens"] = tokens
    cur["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes")
    json.dump(d, open(OUT, "w"), indent=1)
    print("master context refreshed: %dk" % round(tokens / 1000))


def main():
    if "--refresh-current" in sys.argv[1:]:
        refresh_current()
        return
    path = transcript_path()
    sid = os.path.basename(path)[:-len(".jsonl")]
    tokens = context_tokens(path)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes")

    d = json.load(open(OUT)) if os.path.exists(OUT) else {"current": None, "history": []}
    cur = d.get("current")
    if cur and cur.get("session") != sid:
        ended = dict(cur)
        ended["ended"] = cur.get("updated", now)
        d["history"] = (d.get("history") or [])[-49:] + [ended]
        cur = None
    if not cur:
        cur = {"session": sid, "started": now, "tokens": 0}
    cur["tokens"] = tokens
    cur["updated"] = now
    d["current"] = cur
    json.dump(d, open(OUT, "w"), indent=1)
    print("master context: %dk (session %s…)" % (round(tokens / 1000), sid[:8]))


if __name__ == "__main__":
    main()
