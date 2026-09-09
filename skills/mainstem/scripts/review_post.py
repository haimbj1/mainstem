#!/usr/bin/env python3
"""Post a review decision straight from the server — zero model tokens.

Handles the four posting decisions (approve, approve_with_comments, request_changes,
post_findings). The mechanics are deterministic: drafts come out of the review .md,
comment lines are validated against the PR diff, and the unplaceable ones move into
the review body. Anything this module cannot do safely raises Unpostable, and the
server hands the request to the master session instead — never a half-post.

Set MS_REVIEW_DRY_RUN=1 to run everything except the final POST.
"""
import json
import os
import re
import subprocess


class Unpostable(Exception):
    """Send the request back to the master instead of failing it."""


def run(cmd, stdin=None, timeout=120):
    p = subprocess.run(cmd, capture_output=True, text=True, input=stdin, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def repo_pr(url):
    m = re.match(r"https://github\.com/([^/\s]+/[^/\s]+)/pull/(\d+)", url or "")
    if not m:
        raise Unpostable("target is not a PR url: %r" % (url or "")[:80])
    return m.group(1), int(m.group(2))


def parse_drafts(text):
    """{'F1': {path, line|None, body}} from '### F1 — <path>[:<line>]' sections."""
    out = {}
    for m in re.finditer(r"^### (F\d+) — (\S+)\s*\n(.*?)(?=^### |^## |\Z)", text, re.M | re.S):
        fid, loc, body = m.group(1), m.group(2), m.group(3).strip()
        # the excerpt is drawer-side evidence; GitHub shows the code itself
        body = re.sub(r"\A```excerpt[^\n]*\n.*?\n?```\n?", "", body, flags=re.S).strip()
        pm = re.match(r"(.+?):(\d+)$", loc)
        out[fid] = {
            "path": pm.group(1) if pm else loc.rstrip("/"),
            "line": int(pm.group(2)) if pm else None,
            "body": body,
        }
    return out


def diff_lines(repo, pr):
    """{path: set(RIGHT-side commentable lines)} from the PR diff hunks."""
    rc, out, err = run(
        ["gh", "api", "repos/%s/pulls/%d/files" % (repo, pr), "--paginate",
         "--jq", '.[] | {filename, patch}'],
        timeout=120,
    )
    if rc != 0:
        raise Unpostable("gh files failed: " + (err or out)[:200])
    valid = {}
    for line in out.splitlines():
        if not line.strip():
            continue
        f = json.loads(line)
        lines, ln = set(), 0
        for h in (f.get("patch") or "").split("\n"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", h)
            if m:
                ln = int(m.group(1))
                continue
            if h.startswith("-") or h.startswith("\\"):
                continue
            lines.add(ln)
            ln += 1
        valid[f["filename"]] = lines
    return valid


def _mark(path, fids, status=None, verdict=None):
    """Flip posted findings 📋→💬 in the table and update frontmatter. Best-effort."""
    if not path or not os.path.exists(path):
        return
    t = open(path).read()
    for fid in fids:
        n = fid[1:]
        t = re.sub(
            r"^(\|\s*%s\s*\|.*?)\U0001F4CB drafted" % re.escape(n),
            lambda m: m.group(1) + "\U0001F4AC posted",
            t, count=1, flags=re.M,
        )
    if status:
        t = re.sub(r"^status:.*$", "status: " + status, t, count=1, flags=re.M)
    if verdict:
        t = re.sub(r"^verdict:.*$", "verdict: " + verdict, t, count=1, flags=re.M)
    open(path, "w").write(t)


def execute(rec):
    """Returns (status, reply) for the request record. Raises Unpostable to defer to the master."""
    extra = rec.get("extra") or {}
    decision = extra.get("decision") or rec.get("decision") or ""
    url = (rec.get("targets") or [""])[0]
    repo, pr = repo_pr(url)
    path = extra.get("review_path") or rec.get("review_path") or ""
    selected = extra.get("drafts") or rec.get("drafts") or []
    dry = bool(os.environ.get("MS_REVIEW_DRY_RUN"))

    if decision == "approve" and not selected:
        if dry:
            return "done", "DRY RUN: would approve %s/pull/%d with no comments." % (repo, pr)
        rc, out, err = run(["gh", "pr", "review", url, "--approve"], timeout=60)
        if rc != 0:
            return "error", "approve failed: " + (err or out)[:300]
        _mark(path, [], status="approved", verdict="approved")
        return "done", "Approved %s#%d, no comments. Posted by the server - no model tokens." % (repo.split("/")[-1], pr)

    if not path or not os.path.exists(path):
        raise Unpostable("no review file at %r" % path)
    drafts = parse_drafts(open(path).read())
    chosen = [(f, drafts[f]) for f in selected if f in drafts]
    if not chosen:
        raise Unpostable("selected drafts %r not found in %s" % (selected, os.path.basename(path)))

    valid = diff_lines(repo, pr)
    comments, moved = [], []
    for fid, d in chosen:
        if d["line"] and d["line"] in valid.get(d["path"], set()):
            comments.append({"path": d["path"], "line": d["line"], "side": "RIGHT", "body": d["body"]})
        else:
            loc = d["path"] + (":%d" % d["line"] if d["line"] else "")
            moved.append("`%s` (outside the diff hunks, so noted here): %s" % (loc, d["body"]))

    event = {
        "approve": "APPROVE",
        "approve_with_comments": "APPROVE",
        "request_changes": "REQUEST_CHANGES",
        "post_findings": "COMMENT",
    }.get(decision)
    if not event:
        raise Unpostable("unknown decision %r" % decision)

    body = "\n\n".join(moved)
    if not body and event in ("REQUEST_CHANGES", "COMMENT"):
        body = "See the inline comments."
    if not comments and not moved:
        raise Unpostable("nothing to post")

    payload = {"event": event, "body": body, "comments": comments}
    rc, out, _ = run(["gh", "pr", "view", url, "--json", "headRefOid", "-q", ".headRefOid"], timeout=30)
    if rc == 0 and out.strip():
        payload["commit_id"] = out.strip()

    if dry:
        return "done", "DRY RUN: %s on %s#%d with %d inline + %d in body (%s)." % (
            event, repo.split("/")[-1], pr, len(comments), len(moved),
            ", ".join(f for f, _ in chosen))
    rc, out, err = run(
        ["gh", "api", "repos/%s/pulls/%d/reviews" % (repo, pr), "--input", "-"],
        stdin=json.dumps(payload), timeout=120,
    )
    if rc != 0:
        return "error", "post failed: " + (err or out)[:300]
    rid = json.loads(out).get("id", "?")
    status = "approved" if event == "APPROVE" else "posted"
    verdict = {"APPROVE": "approved", "REQUEST_CHANGES": "request-changes"}.get(event)
    _mark(path, [f for f, _ in chosen], status=status, verdict=verdict)
    return "done", "%s posted on %s#%d (review %s): %d inline, %d in the body (%s). Posted by the server - no model tokens." % (
        event.replace("_", " ").title(), repo.split("/")[-1], pr, rid,
        len(comments), len(moved), ", ".join(f for f, _ in chosen))
