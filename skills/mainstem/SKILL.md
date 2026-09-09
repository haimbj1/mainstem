---
name: mainstem
description: Run MainStem — the local board at the configured host:port, the daily bake of Jira/Calendar/mail, and the pending requests the page sends the master session. Use when the user says /mainstem, "refresh the board", "what's my status", or asks for a work overview across repos.
---

# mainstem

Master-session skill. Run from the configured `workRoot`. Detail lives in `REFERENCE.md` — read it
only when this file sends you there.

**The board is local. It costs no model tokens.** The developer opens the configured host:port
(default `127.0.0.1:7777`). The page talks to `ms_server.py`, which runs the collectors and
`build.py` itself. The master session only answers the few request kinds that need judgement.

## Never automate this skill

Do **not** run `/loop`, a cron, or a scheduled agent that invokes `/mainstem` from the master
session. Every fire re-injects this file and the session pings into the master context — measured at
~14% of the daily budget in two minutes. The server's own 30-minute rebuild is the automation.
Refresh only when the developer clicks ↻ or asks.

## The local server

| item | value |
| --- | --- |
| service | `ms_server.py`, the configured launchd label, the configured host:port (default `127.0.0.1:7777`) |
| install / remove | `bash install.sh` · `bash uninstall.sh` (repo root) |
| log | the configured `dataDir`'s `server.log` |
| routes | `GET /` (rebuilds if a `*.json` changed, then serves the page) · `GET /data/<name>.json` · `POST /request` · `GET /health` |
| built page | the configured `dataDir`'s `control-center.html` |

It rebuilds every 30 minutes on its own (`collect.sh` + `reviews_index.py` +
`session_status_from_notes.py` + `build.py`). Single instance, held by an flock on `server.pid`.

## Request kinds — who handles what

`POST /request` appends to `requests.json` and dispatches. The page polls `/data/requests.json`
every 10 s for the reply.

**The server, immediately, no model:**

| kind | what it does |
| --- | --- |
| `jump` | validates `extra.cc` starts with `ms://`, runs `jump.sh` → iTerm2 |
| `refresh` | runs the collectors and rebuilds; `extra.panel` ∈ `prs, sessions, worktrees, reviews, jira` narrows it |
| `delete_worktrees` | re-checks dirty/unpushed per target; refuses those; needs `extra.confirmed` |
| `push_branches` | pushes each target that is ahead |
| `open` | `open <extra.url>` for http(s) only |
| `rotate` | if a master tmux session exists → `rotate_master.sh` (respawn in place); else `ms_master.sh` (launch one). Server-handled so it works even with no master alive. |
| review posting | `decision` ∈ approve / approve_with_comments / request_changes / post_findings → `review_post.py`: stale-head guard, drafts read from the review .md, lines validated against the diff, one `gh` POST, statuses flipped. Zero model tokens. Falls back to the master only when it cannot post safely. |

**The master session, left `status: "pending"`:** `chat`, `review_question`, `quickwins`,
and any `decision` the server could not handle (re-review dispatch, judgement calls,
review_post fallbacks).

## Watching for pending requests

**Exactly one master may watch `requests.json` at a time.** Two armed Monitors both wake on the same
request and can double-post to GitHub. Before arming, run `TaskList`: if a MainStem Monitor is
already running (this session after a resume, or an un-retired old master), do NOT arm a second — reuse
it, or `TaskStop` the stale one first. On rotation, the old master must exit before the new one arms.

Arm one Monitor on `requests.json` and let it wake you. Never poll it yourself, and never read the
whole file — `pending_requests.py` prints only what you own:

```bash
python3 pending_requests.py
```

Then answer per `REFERENCE.md` (§ `kind: decision`, § Review requests, § Pending approvals), write
the `reply` and `status` back into `requests.json`, and stop. The server rebuilds the page on the
next `GET /`.

## `bake` — once a day

Sources the server cannot collect on its own. Run the `ms-refresher` agent in `full` mode; it writes:

- `jira.json` — open tickets assigned to the developer (the Tickets tab renders counts, due-soon and stale
  from this bake, not a live query);
- `calendar.json` — the next three days;
- `brief.json` — `lines` (≤ 2) plus `mail` (≤ 5 lines, the inbox summary that replaced the Gmail
  panel).

A file that is missing shows as "not baked yet" on the page — `build.py` never invents rows.
Quick-win verdicts come from `ms-quickwins` (at most once a day, `quickwins.json`).

## `publish` — optional, on explicit ask only

The artifact is no longer the daily tool. Publish only when the developer asks for a shareable,
**read-only** page (e.g. to check the board from a phone) — never publish the write-enabled build.

1. `python3 build.py --readonly` — bakes `DATA.config.readonly = true` and writes
   `control-center-readonly.html` (next to, never overwriting, the live `control-center.html`).
   This hides every write-sending control in the template. Plain `python3 build.py` (no flag)
   builds the write-enabled local page instead — never publish that file.
2. Extract the last `<script>` block from the read-only file and run `node --check` on it.
   **Never launch a browser** against the page — headless Chrome crashed the developer's browser
   once.
3. Artifact tool, the read-only file's path, favicon `🎛️`, URL in `artifact_url.txt`. Manifest and
   the never-share rule: `REFERENCE.md` § Build and publish.

The same template serves both local and published pages: it branches on `location.hostname` being
loopback for local vs published, and on `DATA.config.readonly` for whether write controls render
at all.


## Keep the master small — rotate, don't grow

Every tool call re-sends the whole master context, so a big master makes everything expensive.
All durable state lives on disk (`requests.json`, review files, `session_status.json`,
`ms_usage.json`, memory, the handoff note) — the conversation holds nothing worth keeping.
Therefore: **prefer a fresh master session over compaction**, and rotate at ~150k context
(a heavy day ≈ +50k). The local server and launchd job run on regardless of rotation.

**Launch the master in the tmux harness** so rotation can respawn it in place:
`bash ms_master.sh` — creates the configured master tmux session (if absent) and opens it in an
iTerm tab. The board's **⟳ Rotate master** button does this too: it launches a master when none is
running, and respawns the existing one in place otherwise. Both go through the server, so no master
need be alive.

**Keep the handoff fresh.** After you write `reply`+`status` for any request, also run
`bash handoff.sh none "<current one-line verbal asks>"`. Rotation can be triggered from the button at
any moment; the handoff note is the only thing the next master inherits, so it must always be current.

### Retire the master manually (if not using the button)
1. `bash handoff.sh none "<one line: open items + verbal asks>"`
2. Exit this session; `bash ms_master.sh` (or the ⟳ button) starts the replacement.

### New master — start ritual
Precondition: the old master has exited (never two armed Monitors at once — see § Watching). During
the gap the server still handles refresh/jump/defer/delete/jira; only chat/decision/review/quickwins
queue in `requests.json`, and drain the moment the new Monitor is armed — nothing is lost.

1. Read the configured `masterHandoffNote` path (the handoff note). Do not redo what it says is done.
2. `TaskList` — confirm no MainStem Monitor is already running, then arm it (persistent):
   ```
   prev=""; while true; do cur=$(python3 pending_requests.py 2>&1 | grep -v '^no pending' || true); [ "$cur" != "$prev" ] && [ -n "$cur" ] && echo "$cur"; prev="$cur"; sleep 20; done
   ```
3. `curl -s <configured host:port>/health` — if the server is down, `bash install.sh` (repo root).
4. That is all. Do not re-read old requests, do not refresh, do not message other sessions.

After every agent result: `python3 log_usage.py <tokens> <model> "<what>"` (feeds the ✦ widget).
Master context cost is tracked for free: `handoff.sh` runs `master_usage.py`, which reads the
master's own transcript into `master_usage.json` (`current` + per-rotation `history`). A new
session id archives the old master and zeroes `current` — no manual step.

## Files

`ms_server.py` `collect.sh` `build.py` `template.html` `jump.sh` `reviews_index.py`
`session_status_from_notes.py` `pending_requests.py` `handoff.sh` `master_usage.py` — all in this
skill's own directory. `install.sh` and `uninstall.sh` are at the repo root. Data and the built page
in the configured `dataDir`.

## Setup (`/mainstem setup`)

Run this as a conversation, not a config-file edit, every time the developer invokes
`/mainstem setup` (first run or a re-run to change answers).

1. **Doctor pass.** Run `scripts/ms_doctor.sh`. Report every `MISSING`/`missing` line in plain
   language: what breaks without it, and the exact install command from the script's own output.
   Never run an install command without an explicit yes from the developer. A missing optional tool
   (tmux, iTerm2) means "that one feature degrades," never "refuse to continue."
2. **Interview**, one question at a time, validating each answer live before writing it:
   - Work root: offer `$HOME/work` if it exists and contains git repos, else ask.
   - Brand name: default "MainStem", accept any string.
   - GitHub login: offer `gh api user -q .login` as a default; confirm it resolves
     (`gh api users/<login>` returns 200) before accepting a manual override.
   - GitHub orgs: ask which orgs to track; confirm each with `gh api orgs/<org>` (or accept it as a
     personal-account list with no org check needed) before writing it.
   - Jira: ask if they use Jira; if yes, ask host (e.g. `yourcompany.atlassian.net`) and validate
     with an unauthenticated `curl -sf https://<host>` before accepting; ask project keys
     (skippable — an empty list disables ticket parsing entirely).
   - Modules: ask which of `jira`/`calendar`/`mail`/`quickwins`/`reviews`/`jump` to enable — default
     `reviews: true, jump: true` (jump only offered on macOS), everything else off until its
     prerequisite is confirmed present.
   - Port: default 7777; confirm it's free (`lsof -i :7777` or attempt a bind) before accepting.
3. **Write + verify.** Write the answers to `~/.config/mainstem/config.json`. Run
   `bash collect.sh` once. Start the service (`install.sh`, or just `ms_server.py` directly if
   already installed). Open the browser to `http://127.0.0.1:<port>`. Walk the developer through
   what they see, tab by tab.
4. This flow is idempotent — running `/mainstem setup` again reads the existing config as
   defaults for each question, so it edits in place rather than starting over.
