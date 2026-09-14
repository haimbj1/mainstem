#!/usr/bin/env python3
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session_ledger  # noqa: E402


def write_sessions(d, sess):
    with open(os.path.join(d, "sessions.json"), "w") as f:
        json.dump(sess, f)


def read_ledger(d):
    with open(os.path.join(d, "session_ledger.json")) as f:
        return json.load(f)


def main():
    d = tempfile.mkdtemp(prefix="ms-ledger-test-")
    a = {"sessionId": "sid-a", "name": "alpha", "cwd": "/x/a", "tmux": "alpha:@0", "kind": "interactive"}
    b = {"sessionId": "sid-b", "name": "beta", "cwd": "/x/b", "tmux": None, "kind": "background"}

    write_sessions(d, [a, b])
    session_ledger.update(d)
    led = read_ledger(d)
    assert led["sid-a"]["alive"] and led["sid-b"]["alive"]
    assert led["sid-a"]["tmux"] == "alpha"
    first_seen_b = led["sid-b"]["lastSeen"]

    # b dies: it stays in the ledger, dead, lastSeen unchanged
    write_sessions(d, [a])
    session_ledger.update(d)
    led = read_ledger(d)
    assert led["sid-a"]["alive"] and not led["sid-b"]["alive"]
    assert led["sid-b"]["lastSeen"] == first_seen_b
    assert led["sid-b"]["cwd"] == "/x/b"

    # ancient entries prune
    led["sid-old"] = {"sessionId": "sid-old", "name": "old", "cwd": "/x", "tmux": "",
                      "kind": "interactive", "alive": False,
                      "lastSeen": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()}
    with open(os.path.join(d, "session_ledger.json"), "w") as f:
        json.dump(led, f)
    session_ledger.update(d)
    led = read_ledger(d)
    assert "sid-old" not in led and "sid-b" in led

    # a session without a sessionId never enters the ledger
    write_sessions(d, [a, {"name": "anon", "cwd": "/x"}])
    session_ledger.update(d)
    assert all(e.get("sessionId") for e in read_ledger(d).values())

    print("test_session_ledger: OK")


if __name__ == "__main__":
    main()
