#!/usr/bin/env python3
"""Bakes collected JSON + template.html into control-center.html. No model calls, no network."""
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import load_config  # noqa: E402

DAILY = {"jira": "jira.json", "calendar": "calendar.json", "gmail": "gmail.json"}
PENDING_DRAFT_MAX_BYTES = 61440


def load(data_dir, name, default):
    p = os.path.join(data_dir, name)
    if not os.path.isfile(p):
        return default
    with open(p) as f:
        return json.load(f)


def load_text(data_dir, name, default):
    p = os.path.join(data_dir, name)
    if not os.path.isfile(p):
        return default
    with open(p) as f:
        return f.read().strip()


def compose_brief(d):
    lines = []
    prs_needing_action = [p for p in d["my_prs"] if p.get("reviewDecision") == "CHANGES_REQUESTED"]
    if prs_needing_action:
        lines.append(f"{len(prs_needing_action)} of your PRs need changes.")
    direct = [r for r in d["review_requests"] if r.get("direct")]
    if direct:
        lines.append(f"{len(direct)} review request(s) waiting on you.")
    busy = [s for s in d["sessions"] if s.get("status") == "busy"]
    if busy:
        lines.append(f"{len(busy)} session(s) busy.")
    pending = d.get("pending") or []
    if pending:
        lines.append(f"{len(pending)} draft(s) waiting on your approval.")
    mail = (load(d["_data_dir"], "brief.json", {}) or {}).get("mail", [])
    when = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return {"lines": lines[:5], "mail": mail, "when": when}


def build(cfg, readonly=False):
    data_dir = cfg["dataDir"]
    d = {
        "_data_dir": data_dir,
        "collected_at": load_text(data_dir, "collected_at.txt", ""),
        "worktrees": load(data_dir, "worktrees.json", []),
        "sessions": load(data_dir, "sessions.json", []),
        "notes": load(data_dir, "session_notes.json", []),
        "session_status": load(data_dir, "session_status.json", {}),
        "my_prs": (load(data_dir, "my_prs.json", {}) or {})
                  .get("data", {}).get("viewer", {}).get("pullRequests", {}).get("nodes", []),
        "review_requests": load(data_dir, "review_requests.json", []),
        "reviews": load(data_dir, "reviews.json", {}),
        "nudges": load(data_dir, "nudges.json", []),
        "jira": load(data_dir, "jira.json", []),
        "calendar": load(data_dir, "calendar.json", []),
        "gmail": load(data_dir, "gmail.json", []),
        "requests": load(data_dir, "requests.json", []),
        "quickwins": load(data_dir, "quickwins.json", {}),
        "artifacts": load(data_dir, "artifacts.json", []),
        "pending": load(data_dir, "pending.json", []),
        "usage": load(data_dir, "ms_usage.json", []),
        "master_usage": load(data_dir, "master_usage.json", {}),
        "bake_stamp": load(data_dir, "bake_stamp.json", None),
    }
    d["brief"] = compose_brief(d)
    d["not_baked"] = [name for key, name in DAILY.items()
                       if not os.path.isfile(os.path.join(data_dir, name))]
    for item in d["pending"]:
        path = item.get("path")
        if path and os.path.isfile(path):
            with open(path, "rb") as f:
                item["body"] = f.read(PENDING_DRAFT_MAX_BYTES).decode("utf-8", "replace")
    d.pop("_data_dir")

    d["config"] = {
        "brand": cfg["brand"],
        "ticketPattern": "|".join(re.escape(p) for p in cfg["jira"]["projects"]) or None,
        "modules": cfg["modules"],
        "githubLogin": cfg["github"]["login"],
        "jiraHost": cfg["jira"]["host"],
        "workRoot": cfg["workRoot"],
        "masterTmuxSession": cfg.get("masterTmuxSession", "ms-master"),
    }
    if readonly:
        d["config"]["readonly"] = True

    template_path = os.path.join(HERE, "template.html")
    with open(template_path) as f:
        template_src = f.read()
    payload = json.dumps(d, ensure_ascii=False).replace("</", "<\\/")
    tpl_escaped = template_src.replace("</", "<\\/")
    out_html = template_src.replace("/*__DATA__*/null", payload).replace("/*__TPL__*/", tpl_escaped)

    out_name = "control-center-readonly.html" if readonly else "control-center.html"
    out_path = os.path.join(data_dir, out_name)
    with open(out_path, "w") as f:
        f.write(out_html)
    size_kb = os.path.getsize(out_path) / 1024
    print(f"wrote {out_path} ({size_kb:.1f} KB)")
    return out_path


if __name__ == "__main__":
    # --readonly bakes DATA.config.readonly = true and writes control-center-readonly.html
    # instead of control-center.html — the page to Artifact-publish for phone/remote viewing,
    # since it hides every write-sending control. Plain `python3 build.py` stays the
    # write-enabled local build; it is never what a publish should use.
    build(load_config(), readonly="--readonly" in sys.argv[1:])
