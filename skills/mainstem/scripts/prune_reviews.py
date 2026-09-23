#!/usr/bin/env python3
"""Drop reviews whose PR is merged, closed, or gone — one batched gh GraphQL call, no model.
The review .md moves to <reviewsDir>/archive/ so the active dir mirrors reality.

A PR can stop resolving entirely: a repo re-created under the same name (a fresh-copy
publish) keeps the name but restarts PR numbering, so the old number is NOT_FOUND.
gh then exits non-zero even though the response carries data for every other alias.
NOT_FOUND aliases are treated as gone; any other GraphQL error still fails the run."""
import json, os, re, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import load_config  # noqa: E402

PR_URL = re.compile(r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)$")


def classify_errors(payload):
    """Split GraphQL errors into aliases gone from GitHub vs errors that must fail the run."""
    not_found, fatal = set(), []
    for e in payload.get("errors") or []:
        path = e.get("path") or []
        if e.get("type") == "NOT_FOUND" and path:
            not_found.add(path[0])
        else:
            fatal.append(e.get("message", "unknown graphql error"))
    return not_found, fatal


def fetch_states(urls):
    parts = []
    for i, u in enumerate(urls):
        owner, repo, num = PR_URL.match(u).groups()
        parts.append('r%d: repository(owner:"%s", name:"%s"){ pullRequest(number:%s){ state headRefOid } }'
                     % (i, owner, repo, num))
    q = "query{ %s }" % " ".join(parts)
    out = subprocess.run(["gh", "api", "graphql", "-f", "query=" + q], capture_output=True, text=True)
    try:
        payload = json.loads(out.stdout or "{}")
    except ValueError:
        payload = {}
    # gh exits non-zero whenever the errors array is present, even with usable partial
    # data — so the exit code alone must not fail the run.
    if not isinstance(payload.get("data"), dict):
        sys.exit("prune_reviews: gh failed: " + (out.stderr or out.stdout)[:300])
    not_found, fatal = classify_errors(payload)
    if fatal:
        sys.exit("prune_reviews: graphql errors: " + "; ".join(fatal)[:300])
    return payload["data"], not_found


def main():
    cfg = load_config()
    D = cfg["dataDir"]
    active = os.path.join(cfg["reviewsDir"], "active")
    archive = os.path.join(cfg["reviewsDir"], "archive")

    rv = json.load(open(f"{D}/reviews.json"))
    urls = [u for u in rv if PR_URL.match(u)]
    if not urls:
        print("prune_reviews: nothing to check")
        return

    data, not_found = fetch_states(urls)

    gone = []
    for i, u in enumerate(urls):
        alias = "r%d" % i
        node = data.get(alias) or {}
        pr = node.get("pullRequest") or {}
        state = "GONE" if alias in not_found else (pr.get("state") or "OPEN")
        if state == "OPEN" and pr.get("headRefOid"):
            rv[u]["live_head"] = pr["headRefOid"]
        if state in ("MERGED", "CLOSED", "GONE"):
            gone.append((u, state))
            e = rv.pop(u)
            os.makedirs(archive, exist_ok=True)
            f = os.path.join(active, "%s-%s.md" % (e.get("repo"), e.get("pr")))
            if os.path.exists(f):
                shutil.move(f, os.path.join(archive, os.path.basename(f)))
    json.dump(rv, open(f"{D}/reviews.json", "w"), indent=1)
    print("prune_reviews: dropped %d (%s); %d active" % (
        len(gone), ", ".join("#%s %s" % (u.rsplit("/", 1)[1], s) for u, s in gone) or "none", len(rv)))


if __name__ == "__main__":
    main()
