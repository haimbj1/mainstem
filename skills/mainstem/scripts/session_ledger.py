#!/usr/bin/env python3
"""Persistent ledger of every Claude session the collector has seen.

sessions.json holds only the sessions alive right now, so a reboot erases the
name → sessionId → cwd mapping and every PR-session link with it. The ledger keeps
that mapping: one entry per sessionId, updated while the session lives, kept (alive:
false) after it dies. The board's restore button resumes dead sessions from it.

Entries older than PRUNE_DAYS drop out. Usage: session_ledger.py <dataDir>
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

PRUNE_DAYS = 14


def update(data_dir):
    with open(os.path.join(data_dir, "sessions.json")) as f:
        live = json.load(f)
    path = os.path.join(data_dir, "session_ledger.json")
    try:
        with open(path) as f:
            ledger = json.load(f)
    except (OSError, ValueError):
        ledger = {}

    now = datetime.now(timezone.utc).isoformat()
    live_ids = set()
    for s in live:
        sid = s.get("sessionId")
        if not sid:
            continue
        live_ids.add(sid)
        ledger[sid] = {
            "sessionId": sid,
            "name": s.get("name", ""),
            "cwd": s.get("cwd", ""),
            "tmux": (s.get("tmux") or "").split(":")[0],
            "kind": s.get("kind", "background"),
            "lastSeen": now,
            "alive": True,
        }
    cutoff = (datetime.now(timezone.utc) - timedelta(days=PRUNE_DAYS)).isoformat()
    for sid in list(ledger):
        if sid not in live_ids:
            ledger[sid]["alive"] = False
        if ledger[sid].get("lastSeen", "") < cutoff:
            del ledger[sid]

    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(ledger, f, indent=1)
    os.replace(tmp, path)
    dead = sum(1 for e in ledger.values() if not e["alive"])
    print("session ledger: %d live, %d dead kept" % (len(live_ids), dead))


if __name__ == "__main__":
    update(sys.argv[1])
