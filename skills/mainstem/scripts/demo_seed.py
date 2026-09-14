#!/usr/bin/env python3
"""Writes a fake but realistic mainstem dataset for --demo mode, screenshots, and CI smoke."""
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import load_config  # noqa: E402

NOW = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write(data_dir, name, obj):
    with open(os.path.join(data_dir, name), "w") as f:
        json.dump(obj, f, indent=1)


def _proc(dt):
    """procStart/startedAt in the same shape the live session registry writes them."""
    return dt.ctime(), int(dt.timestamp() * 1000)


def write_demo_data(data_dir):
    os.makedirs(data_dir, exist_ok=True)
    # a fixed fictional root, never the real config: demo pages get published (docs
    # screenshots, the Pages demo), and a real workRoot embeds the local username
    work_root = "/home/demo/work"
    app_dir = os.path.join(work_root, "demo-app")
    widgets_dir = os.path.join(work_root, "demo-app-widgets")

    # Field names/shapes here must match collect.sh's worktrees section exactly
    # (name, path, remote, branch, dirty:int, kind:"worktree"|"clone", main,
    # behind/ahead:int|null, last_rel, last_iso, last_msg) -- template.html reads those,
    # not is_worktree/last_commit/last_subject.
    _write(data_dir, "worktrees.json", [
        {"name": "demo-app", "path": app_dir, "remote": "demo-org/demo-app",
         "branch": "main", "dirty": 0, "kind": "clone", "main": "",
         "behind": 0, "ahead": 0, "last_rel": "2 days ago",
         "last_iso": "2026-09-06T10:00:00Z", "last_msg": "add health endpoint"},
        {"name": "demo-app-widgets", "path": widgets_dir, "remote": "demo-org/demo-app",
         "branch": "feat/widgets", "dirty": 2, "kind": "worktree", "main": app_dir,
         "behind": 0, "ahead": 1, "last_rel": "3 hours ago",
         "last_iso": "2026-09-08T09:00:00Z", "last_msg": "wip: widget resize"},
    ])

    # sessions.json shape must match collect.sh's registry projection: pid, name, cwd,
    # status, procStart, startedAt, version, sessionId, tmux, tty, host, kind (no "started").
    p1, s1 = _proc(datetime(2026, 9, 8, 8, 55, 0, tzinfo=timezone.utc))
    p2, s2 = _proc(datetime(2026, 9, 8, 9, 10, 0, tzinfo=timezone.utc))
    p3, s3 = _proc(datetime(2026, 9, 7, 22, 0, 0, tzinfo=timezone.utc))
    _write(data_dir, "sessions.json", [
        {"pid": 51001, "name": "feat-widgets", "cwd": widgets_dir, "status": "busy",
         "procStart": p1, "startedAt": s1, "version": "2.1.0", "sessionId": "demo-sid-1",
         "tmux": None, "tty": "/dev/ttys001", "host": "", "kind": "interactive"},
        {"pid": 51002, "name": "ms-refresher", "cwd": work_root, "status": "busy",
         "procStart": p2, "startedAt": s2, "version": "2.1.0", "sessionId": "demo-sid-2",
         "tmux": None, "tty": "", "host": "", "kind": "agent"},
        {"pid": 51003, "name": "master", "cwd": work_root, "status": "idle",
         "procStart": p3, "startedAt": s3, "version": "2.1.0", "sessionId": "demo-sid-3",
         "tmux": "ms-master:@0.%0", "tty": "/dev/ttys002", "host": "", "kind": "interactive"},
    ])

    _write(data_dir, "session_notes.json", [
        {"file": "feat-widgets.md", "mtime": "2026-09-08T09:00:00Z",
         "head": f"---\nbranch: feat/widgets\nworktree: {widgets_dir}\n---\n"
                 "WIP: resizing the widget grid, tests green, PR not opened yet."},
    ])

    _write(data_dir, "session_status.json", {
        "feat-widgets": {"when": NOW, "repo": "demo-app-widgets",
                          "doing": "resizing the widget grid", "refs": ["#12"],
                          "blocked": "none", "source": "note"},
    })

    # Shape = the raw `gh api graphql` envelope collect.sh writes to my_prs.json — build.py
    # unwraps .data.viewer.pullRequests.nodes, so the fixture must carry the same envelope,
    # not the already-unwrapped node list.
    _write(data_dir, "my_prs.json", {"data": {"viewer": {"pullRequests": {"nodes": [
        {"number": 11, "title": "Add health endpoint",
         "url": "https://github.com/example/demo-app/pull/11",
         "isDraft": False, "updatedAt": "2026-09-07T12:00:00Z",
         "createdAt": "2026-09-06T09:00:00Z", "headRefName": "feat/health-endpoint",
         "baseRefName": "main", "additions": 20, "deletions": 3,
         "reviewDecision": "APPROVED", "mergeable": "MERGEABLE",
         "repository": {"nameWithOwner": "demo-org/demo-app"},
         "commits": {"nodes": [{"commit": {"statusCheckRollup": {"state": "SUCCESS"}}}]},
         "reviews": {"nodes": [{"state": "APPROVED", "author": {"login": "contributor-a"}}]},
         "comments": {"totalCount": 2}},
    ]}}}})

    # Shape = collect.sh's jq projection of the review-requested + watch-repo search results.
    # provenance is the field template.html filters/renders on; direct/teams stay for any
    # script that still reads the older ad hoc boolean pair.
    _write(data_dir, "review_requests.json", [
        {"number": 12, "title": "Widget resize follow-up",
         "url": "https://github.com/example/demo-app/pull/12",
         "isDraft": False, "updatedAt": "2026-09-08T09:05:00Z",
         "createdAt": "2026-09-08T08:00:00Z", "headRefName": "feat/widgets",
         "baseRefName": "main", "my_review": None,
         "author": {"login": "contributor-a"},
         "repository": {"nameWithOwner": "demo-org/demo-app"},
         "direct": True, "teams": [], "provenance": "direct"},
        {"number": 44, "title": "Refactor build pipeline",
         "url": "https://github.com/example/other-repo/pull/44",
         "isDraft": False, "updatedAt": "2026-09-05T09:00:00Z",
         "createdAt": "2026-08-20T09:00:00Z", "headRefName": "refactor/build-pipeline",
         "baseRefName": "main", "my_review": None,
         "author": {"login": "contributor-b"},
         "repository": {"nameWithOwner": "demo-org/other-repo"},
         "direct": False, "teams": ["core-team"], "provenance": "team"},
        {"number": 7, "title": "Bump lockfile",
         "url": "https://github.com/example/watched-repo/pull/7",
         "isDraft": False, "updatedAt": "2026-09-01T09:00:00Z",
         "createdAt": "2026-08-25T09:00:00Z", "headRefName": "chore/bump-lockfile",
         "baseRefName": "main", "my_review": None,
         "author": {"login": "contributor-c"},
         "repository": {"nameWithOwner": "demo-org/watched-repo"},
         "direct": False, "teams": [], "provenance": "watch"},
    ])

    _write(data_dir, "reviews.json", {
        "https://github.com/example/demo-app/pull/12": {
            "url": "https://github.com/example/demo-app/pull/12", "repo": "demo-app", "pr": 12,
            "title": "Widget resize follow-up", "author": "contributor-a", "status": "drafted",
            "verdict": "pending", "size": "S", "last_reviewed": NOW,
            "last_head_sha": "deadbeef", "summary": "One finding: an off-by-one in resize math.",
            "findings": [{"n": "1", "sev": "med", "conf": "high", "status": "📋 drafted",
                          "loc": "src/widgets.js:42", "issue": "off-by-one in resize bound"}],
            "sev_counts": {"med": 1},
            "drafts": [{"id": "F1", "loc": "src/widgets.js:42",
                        "text": "This clamps one pixel short of the container edge. Use <= here.",
                        "excerpt": {"start": 40, "target": 42, "diff": True,
                                    "code": " function clampWidth(w, max) {\n"
                                            "   // resize bound\n"
                                            "-  return w < max ? w : max - 1;\n"
                                            "+  return w <= max ? w : max;\n"
                                            " }"},
                        "file_url": "https://github.com/example/demo-app/pull/12/files"
                                    "#diff-3a7f...R42"}],
            "questions": [],
        }
    })

    # Not collector-sourced: when present it's an object ({prs, posted, close_after}), not a
    # list -- null (no nudges) is the accurate "nothing to show" shape, same as build.py's
    # own default when the file is absent.
    _write(data_dir, "nudges.json", None)

    _write(data_dir, "jira.json", [])
    _write(data_dir, "calendar.json", [])
    _write(data_dir, "gmail.json", [])
    # A fresh stamp, so the demo never shows the staleness banner.
    _write(data_dir, "bake_stamp.json", {"when": NOW})
    _write(data_dir, "brief.json", {
        "lines": ["1 PR waiting on your review.", "1 session busy, 0 blocked."], "mail": [],
    })

    _write(data_dir, "requests.json", [
        {"id": "r1", "when": NOW, "kind": "chat", "text": "how's the widget PR looking?",
         "targets": [], "status": "done", "reply": "Approved, one nit left as a comment."},
    ])

    _write(data_dir, "quickwins.json", {
        "generated_at": NOW, "counts": {"close": 0, "quick_win": 0, "stale": 0, "keep": 0},
        "items": [],
    })

    _write(data_dir, "artifacts.json", [])
    _write(data_dir, "pending.json", [])
    _write(data_dir, "ms_usage.json", [])
    _write(data_dir, "master_usage.json", {"current": None, "history": []})

    with open(os.path.join(data_dir, "collected_at.txt"), "w") as f:
        f.write(NOW)


def main():
    cfg = load_config()
    data_dir = cfg["dataDir"]
    write_demo_data(data_dir)
    print(f"demo data written to {data_dir}")


if __name__ == "__main__":
    main()
