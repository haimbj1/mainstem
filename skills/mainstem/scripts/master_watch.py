#!/usr/bin/env python3
"""Master watch loop with an exclusive lock — exactly one master may watch requests.json.

A session's own task list cannot see another session's Monitor, so "check before arming"
by self-report is not a check at all. This script makes the check deterministic: it takes
an flock on <dataDir>/master.lock before it starts the loop. A second master's attempt
fails the flock and exits with instructions. The kernel releases an flock when the holder
dies (kill -9 and reboot included), so a stale lock FILE never blocks — its pid content is
diagnostics for the refusal message, not the lock itself.

Usage:
  master_watch.py           run the watch loop (this is the Monitor command)
  master_watch.py --probe   try the lock, report holder or free, release, exit
"""
import errno
import fcntl
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import load_config  # noqa: E402

INTERVAL_SECONDS = 20
NO_PENDING = "no pending requests for the master session"


def lock_path(cfg):
    return os.path.join(cfg["dataDir"], "master.lock")


def holder_pid(path):
    """Best-effort pid of the current holder, for the refusal message only."""
    try:
        with open(path) as f:
            return int(f.read().strip() or 0) or None
    except (OSError, ValueError):
        return None


def acquire(path):
    """Return an open, flocked handle, or None if another live master holds the lock."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    f = open(path, "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        f.close()
        if e.errno in (errno.EAGAIN, errno.EACCES):
            return None
        raise
    f.seek(0)
    f.truncate()
    f.write("%d\n" % os.getpid())
    f.flush()
    return f  # keep the handle open for the process lifetime


def refuse(path):
    pid = holder_pid(path)
    alive = False
    if pid:
        try:
            os.kill(pid, 0)
            alive = True
        except OSError:
            pass
    print("REFUSED: another master already watches requests.json.", flush=True)
    print("lock: %s  holder pid: %s (%s)" % (path, pid or "?", "alive" if alive else "unknown"), flush=True)
    print("Do NOT arm a second Monitor. Retire the other master first", flush=True)
    print("(its session must exit or TaskStop its Monitor), then re-run this command.", flush=True)
    return 1


def watch():
    prev = ""
    while True:
        out = subprocess.run(
            [sys.executable, os.path.join(HERE, "pending_requests.py")],
            capture_output=True, text=True,
        )
        cur = "\n".join(
            line for line in (out.stdout + out.stderr).splitlines()
            if line and NO_PENDING not in line
        )
        if cur and cur != prev:
            print(cur, flush=True)
        prev = cur
        time.sleep(INTERVAL_SECONDS)


def main(argv):
    cfg = load_config()
    path = lock_path(cfg)
    lock = acquire(path)
    if lock is None:
        return refuse(path)
    if "--probe" in argv:
        print("lock free — acquired and released (probe): %s" % path, flush=True)
        lock.close()
        return 0
    try:
        watch()
    finally:
        lock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
