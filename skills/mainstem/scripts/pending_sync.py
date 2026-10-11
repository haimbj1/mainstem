#!/usr/bin/env python3
"""Sync GitHub-side pending-review changes back into the review files.

A staged pre-review can leave the PENDING state without the board: the developer
submits it from GitHub's own UI, or abandons it there. The file then keeps a stale
`pending_review` + `staged` frontmatter and the page shows a staged pill forever.
This step runs inside the reviews collect: for every active file that records a
pending review, one gh call checks its real state —

- still PENDING: nothing to do;
- submitted (COMMENTED / APPROVED / CHANGES_REQUESTED): the staged drafts reached
  the author, so flip them 📋→💬 and move status/verdict like a board post would;
- gone (404, abandoned): clear the frontmatter only — the comments died with it.

No model, at most one gh call per staged file.
"""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import load_config  # noqa: E402
import review_post  # noqa: E402

CFG = load_config()
ACTIVE = os.path.join(CFG["reviewsDir"], "active")

FM_URL = re.compile(r"^url:\s*(\S+)", re.M)
FM_PENDING = re.compile(r"^pending_review:\s*(\S+)", re.M)
FM_STAGED = re.compile(r"^staged:\s*(.+)$", re.M)


def sync_file(path):
    text = open(path).read()
    mp = FM_PENDING.search(text)
    if not mp:
        return None
    mu = FM_URL.search(text)
    if not mu:
        return None
    try:
        repo, pr = review_post.repo_pr(mu.group(1))
    except Exception:
        return None
    rid = mp.group(1)
    ms = FM_STAGED.search(text)
    staged = (ms.group(1).split() if ms else [])
    rc, out, err = review_post.run(
        ["gh", "api", "repos/%s/pulls/%d/reviews/%s" % (repo, pr, rid)], timeout=60)
    if rc != 0:
        if "404" in (err or out):
            review_post._set_pending_fm(path, None)
            return "cleared %s#%d: pending review %s is gone from GitHub" % (
                repo.split("/")[-1], pr, rid)
        # a transient gh failure must not strip real state
        return None
    state = json.loads(out).get("state") or ""
    if state == "PENDING":
        return None
    status = "approved" if state == "APPROVED" else "posted"
    verdict = "approved" if state == "APPROVED" else None
    review_post._set_pending_fm(path, None)
    review_post._mark(path, staged, status=status, verdict=verdict)
    return "synced %s#%d: pending review %s was submitted on GitHub (%s); %s now posted" % (
        repo.split("/")[-1], pr, rid, state, " ".join(staged) or "no drafts")


def main():
    changed = 0
    for path in sorted(glob.glob(os.path.join(ACTIVE, "*.md"))):
        msg = sync_file(path)
        if msg:
            print(msg)
            changed += 1
    print("pending_sync: %d file(s) updated" % changed)


if __name__ == "__main__":
    main()
