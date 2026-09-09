#!/usr/bin/env python3
"""Local mainstem server — python3 stdlib only, config-driven host/port/paths.

Local mode exists so the day-to-day board costs no model tokens: the page talks to
this process, and this process runs the same collectors and the same build.py the
skill runs. Only the request kinds that need judgement (chat, decision,
review_question, quickwins) stay pending for the master session to pick up.

--demo seeds a fake dataset (demo_seed.write_demo_data) and bakes the page once
before the server starts; every route then behaves exactly as it does normally.
"""
import argparse
import errno
import fcntl
import hashlib
import http.server
import json
import os
import re
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)  # review_post and friends live beside this file

from config import load_config  # noqa: E402
import build as build_mod  # noqa: E402
import demo_seed  # noqa: E402

try:
    import review_post
except Exception as _review_post_err:  # module ported in a later milestone
    review_post = None
    sys.stderr.write(
        "ms_server: review_post unavailable (%r) — server-side review posting disabled\n"
        % (_review_post_err,)
    )

cfg = load_config()

SKILL_DIR = HERE
HOST = cfg["host"]
PORT = cfg["port"]
DATA_DIR = cfg["dataDir"]
REVIEWS_DIR = cfg["reviewsDir"]
SESSION_NOTES_DIR = cfg["sessionNotesDir"]
MASTER_TMUX_SESSION = cfg["masterTmuxSession"]
OUT_HTML = os.path.join(DATA_DIR, "control-center.html")
REQUESTS = os.path.join(DATA_DIR, "requests.json")
STAMP = os.path.join(DATA_DIR, ".build_stamp")
PIDFILE = os.path.join(DATA_DIR, "server.pid")
LOG = os.path.join(DATA_DIR, "server.log")
REBUILD_EVERY = cfg["rebuildIntervalSeconds"]
NOTE_RECOLLECT_THROTTLE = cfg["noteRecollectThrottleSeconds"]
# build.py emits only the page body: the artifact runtime supplies the shell.
# Serving it raw would put the browser in quirks mode, so add the same shell here.
DOCTYPE = ('<!doctype html>\n<html><head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width, initial-scale=1"></head>')

PANELS = {"prs", "sessions", "worktrees", "reviews", "jira"}
# Kinds this server refuses to guess about; the master session answers them.
MODEL_KINDS = {"chat", "decision", "review_question", "quickwins", "review_pr"}

build_lock = threading.Lock()
req_lock = threading.Lock()

_log_lock = threading.Lock()


def log(msg):
    line = "%s %s\n" % (datetime.datetime.now().astimezone().isoformat(timespec="seconds"), msg)
    with _log_lock:
        with open(LOG, "a") as f:
            f.write(line)
    sys.stderr.write(line)


def run(cmd, cwd=None, timeout=300):
    """Run a command and return (rc, stdout, stderr). Never raises on a non-zero rc."""
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


# ---------------------------------------------------------------- build


def data_hash():
    """Content hash of every board JSON plus the template — the build inputs."""
    h = hashlib.sha256()
    for name in sorted(os.listdir(DATA_DIR)):
        if not name.endswith(".json"):
            continue
        h.update(name.encode())
        with open(os.path.join(DATA_DIR, name), "rb") as f:
            h.update(f.read())
    with open(os.path.join(SKILL_DIR, "template.html"), "rb") as f:
        h.update(f.read())
    return h.hexdigest()


DEMO_CFG = None  # set by main() when --demo is active; every build() call then uses it in
                 # place of cfg, so the demo's all-modules-on override survives every rebuild
                 # this process does (page loads, the 30-minute loop, manual refreshes) — not
                 # just the one-off build main() does before the server starts accepting requests.


def build(force=False):
    """Rebuild control-center.html when an input changed. Returns True if it built."""
    with build_lock:
        want = data_hash()
        if not force and os.path.exists(OUT_HTML):
            try:
                if open(STAMP).read().strip() == want:
                    return False
            except OSError:
                pass
        build_mod.build(DEMO_CFG or cfg)
        with open(STAMP, "w") as f:
            f.write(want)
        log("build: done")
        return True


_last_note_recollect = [0.0]


def notes_stale():
    """A session note or registry entry changed after the last sessions collection."""
    try:
        ref = os.path.getmtime(os.path.join(DATA_DIR, "session_notes.json"))
    except OSError:
        return True
    try:
        return any(
            n.endswith((".md", ".json")) and os.path.getmtime(os.path.join(SESSION_NOTES_DIR, n)) > ref
            for n in os.listdir(SESSION_NOTES_DIR)
        )
    except OSError:
        return False


def recollect_notes_if_stale():
    """Sessions link to PRs through the handoff notes; a page load must show a note written
    a second ago. The sessions collector is local-only (no gh), so this stays cheap —
    throttled so registry churn cannot make every GET pay for it."""
    now = time.time()
    if now - _last_note_recollect[0] < NOTE_RECOLLECT_THROTTLE or not notes_stale():
        return
    _last_note_recollect[0] = now
    try:
        collect("sessions")
    except Exception as e:
        log("note-change recollect failed: %s" % e)


def collect(panel=None):
    """Run the local collectors. A panel narrows collect.sh to one section."""
    steps = [["bash", os.path.join(SKILL_DIR, "collect.sh")] + ([panel] if panel else [])]
    if panel in (None, "reviews"):
        steps.append([sys.executable, os.path.join(SKILL_DIR, "reviews_index.py")])
        steps.append([sys.executable, os.path.join(SKILL_DIR, "prune_reviews.py")])
    if panel in (None, "sessions"):
        steps.append([sys.executable, os.path.join(SKILL_DIR, "session_status_from_notes.py")])
    for cmd in steps:
        name = os.path.basename(cmd[1])
        rc, out, err = run(cmd)
        if rc != 0:
            raise RuntimeError("%s failed (rc=%d): %s" % (name, rc, err or out))
        log("collect: %s: %s" % (name, out.splitlines()[-1] if out else "ok"))
    build(force=True)


# ---------------------------------------------------------------- requests


def load_requests():
    if not os.path.exists(REQUESTS):
        return []
    with open(REQUESTS) as f:
        return json.load(f)


def append_request(rec):
    with req_lock:
        reqs = load_requests()
        reqs.append(rec)
        tmp = REQUESTS + ".tmp"
        with open(tmp, "w") as f:
            json.dump(reqs, f, indent=1, ensure_ascii=False)
        os.replace(tmp, REQUESTS)


def update_request(rid, status, reply):
    with req_lock:
        reqs = load_requests()
        for r in reqs:
            if r.get("id") == rid:
                r["status"] = status
                r["reply"] = reply
        tmp = REQUESTS + ".tmp"
        with open(tmp, "w") as f:
            json.dump(reqs, f, indent=1, ensure_ascii=False)
        os.replace(tmp, REQUESTS)


def new_id():
    return "s%x%04x" % (int(time.time() * 1000), os.getpid() & 0xFFFF)


# ---------------------------------------------------------------- git helpers


def git(path, *args):
    return run(["git", "-C", path] + list(args))


def worktree_blockers(path):
    """Why this worktree must not be removed. Empty list = safe."""
    if not os.path.isdir(path):
        return ["does not exist"]
    bad = []
    rc, out, err = git(path, "status", "--porcelain")
    if rc != 0:
        return ["not a git worktree: %s" % (err or out)]
    if out:
        bad.append("%d dirty file(s)" % len(out.splitlines()))
    rc, out, err = git(path, "log", "--oneline", "@{u}..")
    if rc != 0:
        bad.append("no upstream — cannot prove the branch is pushed")
    elif out:
        bad.append("%d unpushed commit(s)" % len(out.splitlines()))
    return bad


def main_repo_of(path):
    rc, out, _ = git(path, "rev-parse", "--git-common-dir")
    if rc != 0:
        return None
    common = out if os.path.isabs(out) else os.path.abspath(os.path.join(path, out))
    return os.path.dirname(common)


# ---------------------------------------------------------------- dispatch


def do_jump(rec):
    cc = (rec.get("extra") or {}).get("cc") or rec.get("cc") or ""
    if not cc.startswith("ms://"):
        raise ValueError("refused: extra.cc must start with ms:// (got %r)" % cc[:60])
    rc, out, err = run(["bash", os.path.join(SKILL_DIR, "jump.sh"), cc], timeout=30)
    if rc != 0:
        raise RuntimeError("jump.sh failed: %s" % (err or out or "rc=%d" % rc))
    return "done", "opened"


def do_refresh(rec):
    panel = (rec.get("extra") or {}).get("panel")
    if panel is not None and panel not in PANELS:
        raise ValueError("unknown panel %r (want one of %s)" % (panel, ", ".join(sorted(PANELS))))
    collect(panel)
    return "done", "Refreshed %s%s" % (time.strftime("%H:%M"), " · %s only" % panel if panel else "")


def do_delete_worktrees(rec):
    targets = rec.get("targets") or []
    if not targets:
        raise ValueError("no worktrees given")
    confirmed = bool((rec.get("extra") or {}).get("confirmed"))
    blocked = {t: worktree_blockers(t) for t in targets}
    safe = [t for t in targets if not blocked[t]]
    risky = ["%s — %s" % (os.path.basename(t), "; ".join(b)) for t, b in blocked.items() if b]
    if not confirmed:
        lines = ["Would remove: " + (", ".join(os.path.basename(t) for t in safe) or "nothing")]
        if risky:
            lines.append("Refused (send again with confirmed): " + " | ".join(risky))
        lines.append("Click Send again to confirm.")
        return "needs_confirmation", " ".join(lines)
    removed, failed = [], []
    for t in safe:
        main = main_repo_of(t)
        if not main:
            failed.append("%s — cannot find its main repo" % t)
            continue
        rc, out, err = git(main, "worktree", "remove", t)
        (removed if rc == 0 else failed).append(t if rc == 0 else "%s — %s" % (t, err or out))
    reply = "Removed %d: %s" % (len(removed), ", ".join(os.path.basename(t) for t in removed) or "none")
    if risky:
        reply += " · refused: " + " | ".join(risky)
    if failed:
        reply += " · failed: " + " | ".join(failed)
    if removed:
        recollect_after_mutation("worktrees")
    return ("error" if (risky or failed) else "done"), reply


def recollect_after_mutation(panel):
    """A delete or push changes the data the page shows, so the answer must arrive with fresh data."""
    try:
        collect(panel)
        build(force=True)
    except Exception as e:  # the mutation itself succeeded; report, do not hide
        log("recollect after %s failed: %s" % (panel, e))


def do_push_branches(rec):
    targets = rec.get("targets") or []
    if not targets:
        raise ValueError("no worktrees given")
    pushed, skipped, failed = [], [], []
    for t in targets:
        name = os.path.basename(t)
        rc, out, err = git(t, "rev-list", "--count", "@{u}..HEAD")
        if rc != 0:
            failed.append("%s — no upstream (%s)" % (name, err or out))
            continue
        if out.strip() == "0":
            skipped.append(name)
            continue
        rc, out, err = git(t, "push")
        (pushed if rc == 0 else failed).append(name if rc == 0 else "%s — %s" % (name, err or out))
    parts = ["pushed: " + (", ".join(pushed) or "none")]
    if skipped:
        parts.append("not ahead: " + ", ".join(skipped))
    if failed:
        parts.append("failed: " + " | ".join(failed))
    if pushed:
        recollect_after_mutation("worktrees")
    return ("error" if failed else "done"), " · ".join(parts)


def do_open(rec):
    url = (rec.get("extra") or {}).get("url") or rec.get("url") or ""
    if not re.match(r"^https?://", url):
        raise ValueError("refused: extra.url must be http(s) (got %r)" % url[:60])
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    rc, out, err = run([opener, url], timeout=20)
    if rc != 0:
        raise RuntimeError("%s failed: %s" % (opener, err or out))
    return "done", "opened " + url


def _tmux_has(session):
    rc, _, _ = run(["tmux", "has-session", "-t", session], timeout=10)
    return rc == 0


def do_rotate(rec):
    """Launch the master if none is running, else respawn it in place. No model needed —
    the server is always up, so this works even when there is no master to answer a request."""
    if _tmux_has(MASTER_TMUX_SESSION):
        rc, out, err = run(["bash", os.path.join(SKILL_DIR, "rotate_master.sh")], timeout=60)
        if rc != 0:
            return "error", "rotate failed: " + (err or out)[:200]
        return "done", "Rotating the master in place — fresh context, same iTerm tab."
    rc, out, err = run(["bash", os.path.join(SKILL_DIR, "ms_master.sh")], timeout=60)
    if rc != 0:
        return "error", "launch failed: " + (err or out)[:200]
    return "done", ("No master was running — launched one. If no iTerm tab opened, run: "
                    "tmux attach -t %s" % MASTER_TMUX_SESSION)


def do_edit_draft(rec):
    """Rewrite one draft's text in its review .md — the file is what gets posted, so an
    inline edit on the page must land there, not in page state. No model involved."""
    extra = rec.get("extra") or {}
    path = os.path.realpath(extra.get("review_path") or "")
    fid = extra.get("draft") or ""
    text = (extra.get("text") or "").strip()
    active = os.path.realpath(os.path.join(REVIEWS_DIR, "active"))
    if not path.startswith(active + os.sep):
        raise ValueError("refused: review_path must be under reviews/active")
    if not re.fullmatch(r"F\d+", fid) or not text:
        raise ValueError("refused: need draft id F<n> and non-empty text")
    t = open(path).read()
    m = re.search(
        r"(^### %s — \S[^\n]*\n(?:```excerpt[^\n]*\n.*?\n```\n)?)(.*?)(?=^### |^## |\Z)" % re.escape(fid),
        t, re.M | re.S)
    if not m:
        return "error", "draft %s not found in %s" % (fid, os.path.basename(path))
    t = t[:m.start(2)] + text + "\n\n" + t[m.end(2):]
    with open(path, "w") as f:
        f.write(t)
    run([sys.executable, os.path.join(SKILL_DIR, "reviews_index.py")])
    build(force=True)
    return "done", "Draft %s updated in %s." % (fid, os.path.basename(path))


def do_publish(rec):
    """Render the read-only page to its own file and hand back a short pointer — the server
    itself has no Artifact tool, so the caller (a Claude session) reads the file and publishes
    it. The reply must stay short: it is persisted into requests.json and build.py re-embeds
    that file into every future build's data payload, so returning the full page HTML here
    would make every publish compound a whole page into all later builds, unbounded."""
    out_path = build_mod.build(cfg, readonly=True)
    size_kb = os.path.getsize(out_path) / 1024
    return "done", "Read-only page rendered to %s (%.1f KB). Read it and publish via the Artifact tool." % (out_path, size_kb)


DISPATCH = {
    "jump": do_jump,
    "refresh": do_refresh,
    "delete_worktrees": do_delete_worktrees,
    "push_branches": do_push_branches,
    "open": do_open,
    "rotate": do_rotate,
    "edit_draft": do_edit_draft,
    "publish": do_publish,
}


REVIEW_POSTING = {"approve", "approve_with_comments", "request_changes", "post_findings"}


def stale_review_check(rec):
    """A posting decision against a moved head always fails in the executor — catching it
    here costs one gh call and zero model tokens."""
    path = (rec.get("extra") or {}).get("review_path") or rec.get("review_path") or ""
    url = (rec.get("targets") or [""])[0]
    if not path or not os.path.exists(path) or "/pull/" not in url:
        return None
    m = re.search(r"last_head_sha:\s*(\S+)", open(path).read())
    if not m:
        return None
    rc, out, err = run(["gh", "pr", "view", url, "--json", "headRefOid", "-q", ".headRefOid"], timeout=30)
    if rc != 0 or not out.strip():
        return None  # cannot check — let the executor decide
    live = out.strip()
    if live.startswith(m.group(1)) or m.group(1).startswith(live):
        return None
    return ("error", "head moved (%s -> %s) — the review is stale." % (m.group(1)[:8], live[:8]))


def queue_rereview(url):
    """A stale posting click should cost the user nothing: queue the re-review for the
    master automatically instead of sending them hunting for a button. Returns False when
    one is already pending or running for this PR."""
    try:
        with open(os.path.join(DATA_DIR, "requests.json")) as f:
            r = json.load(f)
        lst = r if isinstance(r, list) else r.get("requests", [])
        for q in lst:
            if q.get("kind") == "review_pr" and url in (q.get("targets") or []) \
                    and q.get("status") in ("pending", "working"):
                return False
    except OSError:
        pass
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    append_request({
        "id": new_id(), "kind": "review_pr",
        "text": "Re-review %s (head moved under a posting click)" % url,
        "targets": [url], "extra": {}, "status": "pending",
        "created": now, "when": now, "reply": "",
    })
    return True


def handle(rec):
    kind = rec.get("kind") or ""
    if kind == "decision" and ((rec.get("extra") or {}).get("decision") or rec.get("decision")) in REVIEW_POSTING:
        stale = stale_review_check(rec)
        if stale:
            url = (rec.get("targets") or [""])[0]
            queued = queue_rereview(url)
            return stale[0], stale[1] + (
                " A re-review was queued automatically — decide again when its reply lands."
                if queued else " A re-review is already running — decide again when it lands.")
        if review_post is None:
            # Ported in a later milestone; until then the master handles posting.
            return "pending", ""
        # Posting is deterministic (drafts from the .md, lines validated against the diff),
        # so the server does it itself — a click posts with zero model tokens. Anything the
        # module cannot do safely goes to the master; a failure AT the post stays an error,
        # never a silent retry, so a half-post cannot double.
        try:
            return review_post.execute(rec)
        except review_post.Unpostable as e:
            log("review_post -> master: %s" % e)
            return "pending", ""
        except Exception as e:
            log("review_post error: %r" % e)
            return "error", "server post failed: %s" % str(e)[:200]
    # A defer is page-local snooze state; absorbing it here keeps the master (and its tokens) out of it.
    if kind == "decision" and (rec.get("extra") or {}).get("decision") == "defer":
        until = (rec.get("extra") or {}).get("until") or "the chosen date"
        return "done", "Deferred to %s. Hidden in this browser until then; no GitHub change." % until
    if kind in MODEL_KINDS:
        return "pending", ""
    fn = DISPATCH.get(kind)
    if not fn:
        raise ValueError("unknown request kind %r" % kind)
    return fn(rec)


# ---------------------------------------------------------------- http


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ms-local/1"

    def log_message(self, fmt, *args):
        log("http %s" % (fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        try:
            if path in ("/", "/index.html"):
                recollect_notes_if_stale()
                build()
                with open(OUT_HTML, encoding="utf-8") as f:
                    self._send(200, DOCTYPE + f.read() + "</html>", "text/html; charset=utf-8")
                return
            if path == "/manifest.webmanifest":
                # makes the board installable as a standalone app (Chrome: Install page as app)
                cfg = load_config()
                self._send(200, json.dumps({
                    "name": cfg.get("brand") or "MainStem",
                    "short_name": cfg.get("brand") or "MainStem",
                    "start_url": "/",
                    "display": "standalone",
                    "background_color": "#111418",
                    "theme_color": "#111418",
                    "icons": [{"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml"}],
                }), "application/manifest+json")
                return
            if path == "/icon.svg":
                cfg = load_config()
                letter = (cfg.get("brand") or "MainStem")[:1].upper()
                self._send(200,
                    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
                    '<rect width="100" height="100" rx="22" fill="#111418"/>'
                    '<circle cx="50" cy="50" r="34" fill="none" stroke="#e8a33d" stroke-width="6"/>'
                    '<text x="50" y="63" font-family="system-ui" font-size="40" font-weight="700" '
                    'fill="#e8a33d" text-anchor="middle">%s</text></svg>' % letter,
                    "image/svg+xml")
                return
            m = re.fullmatch(r"/data/([A-Za-z0-9_.-]+)\.json", path)
            if m and ".." not in m.group(1):
                p = os.path.join(DATA_DIR, m.group(1) + ".json")
                if not os.path.exists(p):
                    self._json(404, {"error": "no such data file", "name": m.group(1)})
                    return
                with open(p, "rb") as f:
                    self._send(200, f.read())
                return
            if path == "/health":
                self._json(200, {"ok": True, "pid": os.getpid(), "built": os.path.exists(OUT_HTML)})
                return
            self._json(404, {"error": "not found", "path": path})
        except Exception as e:  # a broken build must show, not serve a stale page silently
            log("GET %s failed: %r" % (path, e))
            self._json(500, {"error": str(e)})

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/request":
            self._json(404, {"error": "not found", "path": self.path})
            return
        # Unconditional loopback gate (README: "POST /request refuses non-loopback callers
        # unconditionally") — independent of whether the optional LAN/token read mode is on.
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            self._json(403, {"error": "refused: /request only accepts loopback callers"})
            return
        # Minimal CSRF/Origin defense: a same-machine fetch('/request', ...) from the page
        # itself either omits Origin or sends one that matches this server's own Host header;
        # a cross-origin page (e.g. a malicious site open in the same browser) sends a
        # different Origin and is refused. Absent Origin (curl, older clients) is allowed.
        origin = self.headers.get("Origin")
        if origin and origin != "http://%s" % (self.headers.get("Host") or ""):
            self._json(403, {"error": "refused: cross-origin request"})
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:
            self._json(400, {"error": "bad JSON body: %s" % e})
            return
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        extra = body.get("extra") or {}
        if not isinstance(extra, dict):
            self._json(400, {"error": "extra must be an object"})
            return
        rec = dict(extra)  # the page reads decision fields at the top level
        rec.update({
            "id": body.get("id") or new_id(),
            "kind": body.get("kind") or "",
            "text": str(body.get("text") or "").strip(),
            "targets": body.get("targets") or [],
            "extra": extra,
            "status": "pending",
            "created": now,
            "when": body.get("when") or now,
            "reply": "",
        })
        append_request(rec)
        try:
            status, reply = handle(rec)
        except Exception as e:
            status, reply = "error", str(e)
            log("request %s (%s) failed: %s" % (rec["id"], rec["kind"], e))
        if status != "pending" or reply:
            update_request(rec["id"], status, reply)
        rec["status"], rec["reply"] = status, reply
        self._json(200 if status != "error" else 500, rec)


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# ---------------------------------------------------------------- lifecycle


def claim_pidfile():
    """One instance only. An flock on the pidfile survives a kill -9; a stale file does not block."""
    f = open(PIDFILE, "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        if e.errno in (errno.EAGAIN, errno.EACCES):
            f.seek(0)
            sys.exit("ms_server already running (pid %s) — %s" % (f.read().strip() or "?", PIDFILE))
        raise
    f.seek(0)
    f.truncate()
    f.write("%d\n" % os.getpid())
    f.flush()
    return f  # keep the handle open for the process lifetime


def rebuild_loop():
    while True:
        time.sleep(REBUILD_EVERY)
        try:
            collect(None)
            log("scheduled refresh done")
        except Exception as e:
            log("scheduled refresh failed: %s" % e)


def main():
    parser = argparse.ArgumentParser(description="mainstem local server")
    parser.add_argument("--demo", action="store_true",
                         help="seed a fake dataset and bake the page before starting")
    args = parser.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    if args.demo:
        demo_seed.write_demo_data(DATA_DIR)
        # Demo mode's whole point is a populated board with zero config — every panel's
        # data is seeded regardless of a fresh install's default module flags, so bake the
        # page as if every module were on. A fresh dict (not a mutation of the loaded cfg)
        # so this affects only what this process bakes while running in --demo, never the
        # real config. Set the module-level override (not just call build_mod.build once)
        # and go through the build() wrapper so the .build_stamp it writes matches what was
        # actually baked — otherwise the very next GET / would see a stale/missing stamp,
        # fall through to its own build_mod.build(cfg) call, and silently re-bake with the
        # real (all-modules-default-off) config one page load after the demo page's first paint.
        global DEMO_CFG
        demo_cfg = dict(cfg)
        demo_cfg["modules"] = {k: True for k in cfg["modules"]}
        DEMO_CFG = demo_cfg
        build(force=True)

    lock = claim_pidfile()
    try:
        srv = Server((HOST, PORT), Handler)
    except OSError as e:
        sys.exit("cannot bind %s:%d — %s" % (HOST, PORT, e))
    srv.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    threading.Thread(target=rebuild_loop, daemon=True).start()
    def stop(*_):
        log("shutting down")
        threading.Thread(target=srv.shutdown, daemon=True).start()  # shutdown() deadlocks if called on the serve_forever thread
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop)
    log("listening on http://%s:%d (pid %d)" % (HOST, PORT, os.getpid()))
    try:
        srv.serve_forever()
    finally:
        lock.close()


if __name__ == "__main__":
    main()
