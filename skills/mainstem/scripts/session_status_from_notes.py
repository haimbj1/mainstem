#!/usr/bin/env python3
"""Fill session_status.json from the handoff notes for sessions that did not answer the ping.

Live ping entries (source="ping") younger than 6 hours are kept as they are.
Every other live session in sessions.json gets a source="note" entry derived from its
<sessionNotesDir>/*.md handoff note (session_notes.json), matched by cwd or branch.
Sessions that are no longer live are dropped.

Usage: python3 session_status_from_notes.py [--dir <mainstem data dir>] [--dry-run]
"""
import argparse
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import load_config  # noqa: E402

cfg = load_config()
DEFAULT_DIR = cfg["dataDir"]
PING_MAX_AGE_H = 6
MAX_WORDS = 12


def build_ticket_re(projects):
    """Ticket regex from configured Jira project keys; matches nothing when none are configured."""
    if not projects:
        return re.compile(r"(?!x)x")
    return re.compile(r"\b(?:%s)-\d+\b" % "|".join(re.escape(p) for p in projects))


TICKET_RE = build_ticket_re(cfg["jira"]["projects"])
PR_RE = re.compile(r"#\d+")


def load(d, name, default):
    p = os.path.join(d, name)
    if not os.path.exists(p):
        return default
    with open(p) as f:
        return json.load(f)


def frontmatter(head):
    """{key: value} from the leading --- block, plus the body lines after it."""
    lines = head.splitlines()
    fm, body = {}, lines
    if lines and lines[0].strip() == "---":
        for i, ln in enumerate(lines[1:], 1):
            if ln.strip() == "---":
                body = lines[i + 1 :]
                break
            if ":" in ln:
                k, v = ln.split(":", 1)
                fm[k.strip().lower()] = v.strip()
        else:
            body = []
    return fm, body


def first_body_line(body):
    for ln in body:
        t = ln.strip()
        if t and not t.startswith("#"):
            return t
    return ""


def clip(text, words=MAX_WORDS):
    parts = re.sub(r"\s+", " ", text).strip().split(" ")
    return " ".join(parts[:words]) + ("…" if len(parts) > words else "")


def age_h(iso, now):
    try:
        t = datetime.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return (now - t).total_seconds() / 3600.0


def extract_refs(note_head, branch):
    """Ordered, deduped refs pulled out of one note's raw text. Repo-qualified PR refs
    ("repo#N") come before bare "#N" refs — a bare number collides across repos — then
    ticket refs, then the branch name. Capped at 16 so one runaway note cannot blow up
    the page."""
    refs = []
    # repo-qualified refs from PR URLs come first: "#6" alone collides across repos
    qualified = [
        f"{m.group(1)}#{m.group(2)}"
        for m in re.finditer(r"github\.com/[^/\s]+/([A-Za-z0-9_.-]+)/pull/(\d+)", note_head)
    ]
    for r in qualified + PR_RE.findall(note_head) + TICKET_RE.findall(note_head) + ([branch] if branch else []):
        if r not in refs and r.upper() not in ("N/A",):
            refs.append(r)
    return refs[:16]


def note_entry(note, wt_by_path, cwd):
    fm, body = frontmatter(note["head"])
    branch = re.split(r"[\s(]", fm.get("branch", ""))[0]
    wt = wt_by_path.get(fm.get("worktree", "")) or wt_by_path.get(cwd)
    repo = (wt or {}).get("name") or os.path.basename(cwd.rstrip("/"))
    line = first_body_line(body)
    doing = clip(re.sub(r"^(DONE|WIP|NEXT|BLOCKED|STATUS)\s*:\s*", "", line, flags=re.I))
    refs = extract_refs(note["head"], branch)
    blocked = "none"
    for ln in body:
        if re.match(r"\s*BLOCKED\b", ln, flags=re.I):
            blocked = clip(re.sub(r"^\s*BLOCKED\s*:?\s*", "", ln, flags=re.I), 14) or "see note"
            break
    return {
        "when": note["mtime"],
        "repo": repo,
        "doing": doing or "(no summary in the handoff note)",
        "refs": refs,
        "blocked": blocked,
        "source": "note",
    }


def match_note(session, notes, wt_by_path, cwd_shared=False, live_names=()):
    """Best note for a session: filename == session name beats everything, and a note named
    after any OTHER live session belongs to that session — nobody else may claim it.
    Then the newest note whose frontmatter worktree is the session cwd, then a note whose
    head merely mentions the cwd, then a branch match (never on main/master — every clone
    sits on main). When several live sessions share one cwd (a shared parent directory), cwd
    and branch prove nothing — only a name match counts."""
    cwd = session["cwd"]
    name = session.get("name", "")
    branch = (wt_by_path.get(cwd) or {}).get("branch")
    hits = []
    for n in notes:
        stem = os.path.splitext(n.get("file", ""))[0]
        if name and stem == name:
            hits.append((4, n["mtime"], n))
            continue
        if stem in live_names or cwd_shared:
            continue
        fm, _ = frontmatter(n["head"])
        nb = re.split(r"[\s(]", fm.get("branch", ""))[0]
        if fm.get("worktree") == cwd:
            hits.append((3, n["mtime"], n))
        # a bare substring match lets a parent directory claim every note under it
        elif re.search(re.escape(cwd) + r"(?=[\s'\"`)\],]|$)", n["head"], re.M):
            hits.append((2, n["mtime"], n))
        elif branch and nb and nb == branch and nb not in ("main", "master"):
            hits.append((1, n["mtime"], n))
    if not hits:
        return None
    hits.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return hits[0][2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    now = datetime.datetime.now(datetime.timezone.utc)
    sessions = load(a.dir, "sessions.json", [])
    notes = load(a.dir, "session_notes.json", [])
    worktrees = load(a.dir, "worktrees.json", [])
    old = load(a.dir, "session_status.json", {})
    wt_by_path = {w["path"]: w for w in worktrees if w.get("path")}

    cwd_counts = {}
    for s in sessions:
        cwd_counts[s["cwd"]] = cwd_counts.get(s["cwd"], 0) + 1
    live_names = {s["name"] for s in sessions}

    out, kept, derived, missing = {}, [], [], []
    for s in sessions:
        name = s["name"]
        prev = old.get(name)
        h = age_h((prev or {}).get("when"), now)
        if prev and prev.get("source") == "ping" and h is not None and h < PING_MAX_AGE_H:
            out[name] = prev
            kept.append(name)
            continue
        note = match_note(s, notes, wt_by_path, cwd_shared=cwd_counts[s["cwd"]] > 1, live_names=live_names - {name})
        if note:
            out[name] = note_entry(note, wt_by_path, s["cwd"])
            derived.append(name)
        else:
            missing.append(name)

    p = os.path.join(a.dir, "session_status.json")
    if a.dry_run:
        json.dump(out, sys.stdout, indent=1, ensure_ascii=False)
        print()
    else:
        with open(p, "w") as f:
            json.dump(out, f, indent=1, ensure_ascii=False)
            f.write("\n")
    print(
        f"{p}: {len(out)} entries · kept {len(kept)} ping ({', '.join(kept) or '-'})"
        f" · derived {len(derived)} from notes ({', '.join(derived) or '-'})"
        f" · no info for {len(missing)} ({', '.join(missing) or '-'})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
