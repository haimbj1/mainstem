#!/usr/bin/env python3
"""Print only the requests the local server cannot answer — the ones the master session owns.

The master reads this instead of requests.json so a Monitor wake costs a few lines,
not the whole file.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import load_config  # noqa: E402

cfg = load_config()
REQUESTS = os.path.join(cfg["dataDir"], "requests.json")
MODEL_KINDS = {"chat", "decision", "review_question", "quickwins", "review_pr"}

if not os.path.exists(REQUESTS):
    sys.exit("no requests.json at " + REQUESTS)

with open(REQUESTS) as f:
    rows = json.load(f)

pending = [r for r in rows if r.get("status") == "pending" and r.get("kind") in MODEL_KINDS]
if not pending:
    print("no pending requests for the master session")
    sys.exit(0)

for r in pending:
    text = " ".join(str(r.get("text") or "").split())
    print("%s  %-16s %s" % (r.get("id"), r.get("kind"), text[:300]))
print("--- %d pending" % len(pending))
