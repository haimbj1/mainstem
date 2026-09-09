#!/usr/bin/env python3
"""Append one model-spend entry: log_usage.py <tokens> <model> <what...>"""
import json, os, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config  # noqa: E402

p = os.path.join(config.load_config()["dataDir"], "ms_usage.json")
rows = json.load(open(p)) if os.path.exists(p) else []
rows.append({"when": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"),
             "tokens": int(sys.argv[1]), "model": sys.argv[2], "what": " ".join(sys.argv[3:])[:80]})
json.dump(rows[-500:], open(p, "w"), indent=1)
print("usage: %dk %s" % (int(sys.argv[1]) / 1000, sys.argv[3] if len(sys.argv) > 3 else ""))
