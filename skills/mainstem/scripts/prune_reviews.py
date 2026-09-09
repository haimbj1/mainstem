#!/usr/bin/env python3
"""Drop reviews whose PR is merged or closed — one batched gh GraphQL call, no model.
The review .md moves to <reviewsDir>/archive/ so the active dir mirrors reality."""
import json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import load_config  # noqa: E402

cfg = load_config()
D = cfg["dataDir"]
ACTIVE = os.path.join(cfg["reviewsDir"], "active")
ARCHIVE = os.path.join(cfg["reviewsDir"], "archive")

rv = json.load(open(f"{D}/reviews.json"))
urls = [u for u in rv if re.match(r"https://github\.com/[^/]+/[^/]+/pull/\d+$", u)]
if not urls:
    print("prune_reviews: nothing to check"); sys.exit(0)

parts = []
for i, u in enumerate(urls):
    owner, repo, num = re.match(r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)$", u).groups()
    parts.append('r%d: repository(owner:"%s", name:"%s"){ pullRequest(number:%s){ state headRefOid } }' % (i, owner, repo, num))
q = "query{ %s }" % " ".join(parts)
out = subprocess.run(["gh", "api", "graphql", "-f", "query=" + q], capture_output=True, text=True)
if out.returncode != 0:
    sys.exit("prune_reviews: gh failed: " + out.stderr[:300])
data = json.loads(out.stdout)["data"]

gone = []
for i, u in enumerate(urls):
    node = data.get("r%d" % i) or {}
    pr = node.get("pullRequest") or {}
    state = pr.get("state") or "OPEN"
    if state == "OPEN" and pr.get("headRefOid"):
        rv[u]["live_head"] = pr["headRefOid"]
    if state in ("MERGED", "CLOSED"):
        gone.append((u, state))
        e = rv.pop(u)
        os.makedirs(ARCHIVE, exist_ok=True)
        f = os.path.join(ACTIVE, "%s-%s.md" % (e.get("repo"), e.get("pr")))
        if os.path.exists(f):
            shutil.move(f, os.path.join(ARCHIVE, os.path.basename(f)))
json.dump(rv, open(f"{D}/reviews.json", "w"), indent=1)
print("prune_reviews: dropped %d (%s); %d active" % (
    len(gone), ", ".join("#%s %s" % (u.rsplit("/", 1)[1], s) for u, s in gone) or "none", len(rv)))
