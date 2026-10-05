#!/usr/bin/env python3
"""How far the ms-reviewer agent got on each PR, so the board can put a card in Reviewing the
moment a run really starts instead of when the master marks the request.

  review_progress.py start  <pr_url>
  review_progress.py step   <pr_url> <step> [--done N --total M]
  review_progress.py finish <pr_url>
  review_progress.py fail   <pr_url> "<why>"

One file per PR under <dataDir>/review_progress/: the agent reviews up to 6 PRs at once, and
separate files mean no two runs ever read-modify-write the same JSON. Each write lands through
a temp file and os.replace, because the page polls the aggregate while the agent writes."""
import argparse
import datetime
import glob
import json
import os
import re
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import load_config  # noqa: E402

PROGRESS_SUBDIR = "review_progress"
# In run order: the board turns a step's index into the progress bar's width.
STEPS = (
    ("context", "Collect context"),
    ("diff", "Read the diff"),
    ("files", "Read the touched files"),
    ("findings", "Draft findings"),
    ("verdict", "Suggest a verdict"),
)
STEP_NAMES = tuple(name for name, _ in STEPS)
# Only reading files has a countable unit of work; elsewhere a count would be made up.
COUNTED_STEP = "files"
# A crashed run never calls finish or fail; past this its file is litter, not progress.
STALE_FILE_SECONDS = 24 * 3600
ERROR_MAX_CHARS = 200
# GitHub owners are letters, digits and hyphens only, so "__" cannot occur inside one and the
# file name maps back to exactly one PR.
PR_URL = re.compile(r"https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+)/pull/(\d+)/?")
TEMP_PREFIX = "."
TEMP_SUFFIX = ".tmp"


def progress_dir(cfg):
    return os.path.join(cfg["dataDir"], PROGRESS_SUBDIR)


def entry_path(pdir, url):
    m = PR_URL.fullmatch(url)
    if not m:
        raise ValueError("not a GitHub PR URL: %r" % url)
    owner, repo, number = m.groups()
    return os.path.join(pdir, "%s__%s__%s.json" % (owner, repo, number))


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_atomic(path, entry):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=TEMP_PREFIX, suffix=TEMP_SUFFIX)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(entry, f)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def write_entry(pdir, entry):
    _write_atomic(entry_path(pdir, entry["url"]), entry)


def _read(path):
    with open(path) as f:
        return json.load(f)


def _fresh(url, now):
    return {"url": url, "started_at": now, "updated_at": now, "step": STEP_NAMES[0],
            "done": None, "total": None, "error": None}


def start(pdir, url):
    """Begin (or restart) a run: a retry after fail clears the old error."""
    write_entry(pdir, _fresh(url, _now()))


def step(pdir, url, name, done=None, total=None):
    if name not in STEP_NAMES:
        raise ValueError("unknown step %r — one of %s" % (name, ", ".join(STEP_NAMES)))
    if (done is None) != (total is None):
        raise ValueError("--done and --total go together")
    if done is not None and name != COUNTED_STEP:
        raise ValueError("--done/--total only count the %r step" % COUNTED_STEP)
    if done is not None and not 0 <= done <= total:
        raise ValueError("need 0 <= done <= total, got %d/%d" % (done, total))
    path = entry_path(pdir, url)
    if not os.path.exists(path):
        raise FileNotFoundError("no progress for %s — call start first" % url)
    entry = _read(path)
    entry.update(step=name, done=done, total=total, error=None, updated_at=_now())
    _write_atomic(path, entry)


def finish(pdir, url):
    """The review file is written: the board takes it from here. Idempotent, so a repeated
    finish after a retry does not fail the agent's last step."""
    try:
        os.remove(entry_path(pdir, url))
    except FileNotFoundError:
        pass


def fail(pdir, url, why):
    """Works without a start too: an abort can come before the first step."""
    path = entry_path(pdir, url)
    now = _now()
    entry = _read(path) if os.path.exists(path) else _fresh(url, now)
    entry.update(error=(why.strip() or "no reason given")[:ERROR_MAX_CHARS], updated_at=now)
    _write_atomic(path, entry)


def load_all(pdir):
    """Every entry the page should see. A file can vanish between the glob and the open (a
    finish), and a foreign file can sit in the dir: skip both rather than fail the poll."""
    entries = []
    for path in glob.glob(os.path.join(pdir, "*.json")):
        try:
            entry = _read(path)
        except (OSError, ValueError):
            continue
        if isinstance(entry, dict) and entry.get("url"):
            entries.append(entry)
    return sorted(entries, key=lambda e: e.get("started_at") or "")


def prune_stale(pdir, max_age=STALE_FILE_SECONDS):
    """Drop entries no run touched within max_age, plus temp files a killed writer left."""
    cutoff = time.time() - max_age
    stale = [p for pattern in ("*.json", TEMP_PREFIX + "*" + TEMP_SUFFIX)
             for p in glob.glob(os.path.join(pdir, pattern)) if os.path.getmtime(p) < cutoff]
    for p in stale:
        os.remove(p)
    return len(stale)


def _parser():
    ap = argparse.ArgumentParser(description="Report ms-reviewer progress to the board.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("start").add_argument("url")
    sp = sub.add_parser("step", help="steps in order: " + "; ".join("%s = %s" % s for s in STEPS))
    sp.add_argument("url")
    sp.add_argument("step", choices=STEP_NAMES)
    sp.add_argument("--done", type=int)
    sp.add_argument("--total", type=int)
    sub.add_parser("finish").add_argument("url")
    fp = sub.add_parser("fail")
    fp.add_argument("url")
    fp.add_argument("why")
    return ap


def main(argv):
    args = _parser().parse_args(argv)
    pdir = progress_dir(load_config())
    try:
        if args.cmd == "start":
            start(pdir, args.url)
        elif args.cmd == "step":
            step(pdir, args.url, args.step, args.done, args.total)
        elif args.cmd == "finish":
            finish(pdir, args.url)
        else:
            fail(pdir, args.url, args.why)
    except (ValueError, FileNotFoundError) as e:
        sys.exit("review_progress: %s" % e)


if __name__ == "__main__":
    main(sys.argv[1:])
