#!/usr/bin/env python3
"""Index <reviewsDir>/active/*.md into <dataDir>/reviews.json, keyed by PR URL."""
import glob, hashlib, json, os, re, datetime, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import load_config  # noqa: E402

cfg = load_config()
SRC = os.path.join(cfg["reviewsDir"], "active")
OUT = os.path.join(cfg["dataDir"], "reviews.json")

DRAFT_RE = re.compile(
    r"^### (F\d+)\s*[—-]\s*(.+?)\n(.*?)(?=^### |\Z)", re.S | re.M)
EXCERPT_RE = re.compile(
    r"```excerpt start=(\d+) target=(\d+)( diff=1)?\n(.*?)\n?```\n?", re.S)


def parse_drafts(body, url):
    drafts = []
    for mm in DRAFT_RE.finditer(body):
        fid, loc, text = mm.group(1), mm.group(2).strip(), mm.group(3).strip()
        excerpt = None
        em = re.match(EXCERPT_RE, text)
        if em:
            excerpt = {"start": int(em.group(1)), "target": int(em.group(2)),
                       "diff": bool(em.group(3)), "code": em.group(4)}
            text = text[em.end():].strip()
        file_url = None
        lm = re.match(r"(.+?):(\d+)$", loc)
        if lm and url:
            # GitHub's Files-changed tab anchors a file by the sha256 of its path, R<line> per line
            digest = hashlib.sha256(lm.group(1).encode()).hexdigest()
            file_url = "%s/files#diff-%sR%s" % (url, digest, lm.group(2))
        drafts.append({"id": fid, "loc": loc, "text": text, "excerpt": excerpt,
                       "file_url": file_url})
    return drafts


def parse(path):
    text = open(path).read()
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not m:
        return None
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    body = m.group(2)

    def section(name):
        mm = re.search(rf"^## {re.escape(name)}\s*\n(.*?)(?=^## |\Z)", body, re.S | re.M)
        return mm.group(1).strip() if mm else ""

    findings = []
    for row in section("Findings").splitlines():
        if not row.startswith("|") or re.match(r"^\|\s*#", row) or re.match(r"^\|[-\s|]+\|$", row):
            continue
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) >= 6 and cells[0].isdigit():
            findings.append({"n": int(cells[0]), "sev": cells[1], "conf": cells[2], "status": cells[3], "loc": cells[4], "issue": cells[5]})
    url = fm.get("url", "")
    if not url and fm.get("repo") and fm.get("pr"):
        # frontmatter's repo: field carries the full owner/repo slug
        url = f"https://github.com/{fm['repo']}/pull/{fm['pr']}"
    drafts = parse_drafts(section("Inline comment drafts"), url)
    questions = [q[2:].strip() for q in section("Questions").splitlines() if q.startswith("- ") and q.strip() != "- None."]
    sev_counts = {}
    for f in findings:
        sev_counts[f["sev"]] = sev_counts.get(f["sev"], 0) + 1
    return {
        "url": url, "repo": fm.get("repo"), "pr": int(fm["pr"]) if fm.get("pr", "").isdigit() else fm.get("pr"),
        "title": fm.get("title"), "author": fm.get("author"), "status": fm.get("status"), "verdict": fm.get("verdict", "pending"),
        "size": fm.get("size"), "last_reviewed": fm.get("last_reviewed"), "last_head_sha": fm.get("last_head_sha"),
        "request": fm.get("request"), "depends_on": fm.get("depends_on"), "opened": fm.get("opened"),
        "depth": fm.get("depth"), "depth_why": fm.get("depth_why"),
        "summary": section("Summary"), "findings": findings, "sev_counts": sev_counts, "drafts": drafts, "questions": questions,
        "path": path, "mtime": datetime.datetime.fromtimestamp(os.path.getmtime(path), datetime.timezone.utc).isoformat(),
    }


out = {}
for p in sorted(glob.glob(os.path.join(SRC, "*.md"))):
    r = parse(p)
    if r and r["url"]:
        out[r["url"]] = r
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(out, open(OUT, "w"), indent=1, ensure_ascii=False)
print(OUT, len(out), "reviews")
