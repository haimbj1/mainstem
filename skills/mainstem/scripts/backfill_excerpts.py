#!/usr/bin/env python3
"""Insert a code excerpt under each finding draft in the active review files.

For every `### F<n> — <path>:<line>` section, embed the code around the target:
preferably the PR's own diff hunk rows (markers kept, so the board colors -/+ like
GitHub), falling back to plain head-file lines when the target is outside every hunk.

    ```excerpt start=<first new-side line> target=<line> diff=1
     context row
    -removed row
    +added row
    ```

(`diff=1` marks marker-prefixed rows; the fallback omits it and carries bare lines.)

Idempotent: sections that already carry an excerpt are skipped; --redo regenerates them.
Usage: backfill_excerpts.py [--redo] [file.md ...]  (default: all active reviews).
"""
import base64
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import load_config  # noqa: E402

CTX = 4


def run(cmd, timeout=120):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


_patches = {}


def pr_patches(repo, pr):
    """{path: patch} for the PR diff."""
    key = (repo, pr)
    if key not in _patches:
        rc, out, _ = run(["gh", "api", "repos/%s/pulls/%s/files" % (repo, pr),
                          "--paginate", "--jq", '.[] | {filename, patch}'])
        d = {}
        if rc == 0:
            for line in out.splitlines():
                if line.strip():
                    f = json.loads(line)
                    d[f["filename"]] = f.get("patch") or ""
        _patches[key] = d
    return _patches[key]


def hunk_excerpt(patch, target):
    """(start_new_line, rows) of the ±CTX diff rows around the new-side target, or None."""
    rows = []  # (marker, text, new_line or None)
    ln = 0
    for h in patch.split("\n"):
        m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", h)
        if m:
            ln = int(m.group(1))
            continue
        if h.startswith("\\"):
            continue
        if h.startswith("-"):
            rows.append(("-", h[1:], None))
        elif h.startswith("+"):
            rows.append(("+", h[1:], ln)); ln += 1
        else:
            rows.append((" ", h[1:] if h.startswith(" ") else h, ln)); ln += 1
    idx = next((i for i, r in enumerate(rows) if r[2] == target), None)
    if idx is None:
        return None
    lo = max(0, idx - CTX)
    hi = min(len(rows), idx + CTX + 1)
    sel = rows[lo:hi]
    start = next((r[2] for r in sel if r[2] is not None), target)
    return start, ["%s%s" % (r[0], r[1]) for r in sel]


_files = {}


def file_lines(repo, sha, path):
    key = (repo, sha, path)
    if key not in _files:
        rc, out, _ = run(["gh", "api", "repos/%s/contents/%s?ref=%s" % (repo, path, sha)], timeout=60)
        if rc != 0:
            _files[key] = None
        else:
            d = json.loads(out)
            _files[key] = base64.b64decode(d.get("content") or "").decode("utf-8", "replace").split("\n")
    return _files[key]


def process(md, redo=False):
    t = open(md).read()
    murl = re.search(r"^url:\s*(\S+)", t, re.M)
    msha = re.search(r"^last_head_sha:\s*(\S+)", t, re.M)
    if not murl or not msha:
        return 0
    mrepo = re.match(r"https://github\.com/([^/\s]+/[^/\s]+)/pull/(\d+)", murl.group(1))
    if not mrepo:
        return 0
    repo, pr, sha = mrepo.group(1), mrepo.group(2), msha.group(1)

    added = 0

    def repl(m):
        nonlocal added
        header, loc, rest = m.group(1), m.group(2), m.group(3)
        has = re.match(r"\s*```excerpt([^\n]*)\n.*?\n?```\n?", rest, re.S)
        if has and not redo:
            return m.group(0)
        if has:
            rest = rest[has.end():]
        pm = re.match(r"(.+?):(\d+)$", loc)
        if not pm:
            return header + rest
        path, ln = pm.group(1), int(pm.group(2))
        hx = hunk_excerpt(pr_patches(repo, pr).get(path, ""), ln)
        if hx:
            start, rows = hx
            fence = "```excerpt start=%d target=%d diff=1\n%s\n```\n" % (start, ln, "\n".join(rows))
        else:
            lines = file_lines(repo, sha, path)
            if not lines:
                return header + rest
            lo, hi = max(1, ln - CTX), min(len(lines), ln + CTX)
            fence = "```excerpt start=%d target=%d\n%s\n```\n" % (lo, ln, "\n".join(lines[lo - 1:hi]))
        added += 1
        return header + fence + rest

    out = re.sub(r"(^### F\d+ — (\S+)\s*\n)(.*?)(?=^### |^## |\Z)",
                 lambda m: repl(m), t, flags=re.M | re.S)
    if added:
        open(md, "w").write(out)
    return added


def main():
    args = sys.argv[1:]
    redo = "--redo" in args
    cfg = load_config()
    default_glob = os.path.join(cfg["reviewsDir"], "active", "*.md")
    files = [a for a in args if a != "--redo"] or sorted(glob.glob(default_glob))
    total = 0
    for md in files:
        n = process(md, redo=redo)
        total += n
        if n:
            print("%s: %s%d excerpts" % (md.split("/")[-1], "redid " if redo else "+", n))
    print("total: %d" % total)


if __name__ == "__main__":
    main()
