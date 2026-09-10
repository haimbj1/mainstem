# Architecture

## Config resolution

`config.py`'s `load_config()` starts from a built-in `DEFAULTS` dict, then merges up to three
layers on top, lowest priority first, each overriding the previous field-by-field — so the last
one applied wins:

1. `<repo>/config.local.json` (repo-level defaults, lowest priority)
2. `~/.config/mainstem/config.json` (the user's standing config)
3. `$MS_CONFIG` (a path, if the env var is set — the most specific override, wins over both)

A missing layer is skipped, not an error. The merge is a shallow overwrite per top-level key,
except `github`, `jira`, and `modules`, which deep-merge one level down (so setting only
`jira.host` in a layer doesn't clobber `jira.projects` from an earlier layer). Every path-shaped
field (`workRoot`, `dataDir`, `reviewsDir`, `sessionNotesDir`, `masterHandoffNote`) is then
`os.path.expanduser` + `os.path.abspath`-resolved once, so every consumer downstream sees an
absolute path. See the README's config reference table for the full field list and defaults.

## `dataDir` files

Everything the built page renders is a plain JSON file (or, for one, a text file) under the
configured `dataDir`. `demo_seed.py` writes a realistic instance of every one of them for
`--demo` mode, screenshots, and the CI smoke test; the shapes below are exactly what it writes,
since that inventory was authoritative at the time the collectors were built.

| File | Shape |
| --- | --- |
| `worktrees.json` | List of `{name, path, remote, branch, dirty:int, kind:"worktree"\|"clone", main, behind:int\|null, ahead:int\|null, last_rel, last_iso, last_msg}` — one row per repo/worktree under `workRoot`. |
| `sessions.json` | List of `{pid, name, cwd, status, procStart, startedAt, version, sessionId, tmux, tty, host, kind}` — one row per live Claude Code session in the local registry; see § Session kind below. |
| `session_notes.json` | List of `{file, mtime, head}` — one row per `<sessionNotesDir>/*.md`, `head` being the note's frontmatter plus its first paragraph. |
| `session_status.json` | Object keyed by session name; each value `{when, repo, doing, refs, blocked, source}` — the parsed one-line status extracted from that session's note (`source: "note"`). |
| `my_prs.json` | The raw `gh api graphql` envelope `collect.sh` writes: `{data:{viewer:{pullRequests:{nodes:[...]}}}}`, one node per open PR authored by `github.login` — `repository.nameWithOwner`, `reviews.nodes`, `commits.nodes[].commit.statusCheckRollup.state`, `reviewDecision`, `mergeable`, etc. `build.py` unwraps it down to the node list before handing it to the template as `DATA.my_prs`. |
| `review_requests.json` | List of PRs awaiting a review from the developer — direct request, team request, or a `reviews.watchRepos` repo — each carrying `direct:bool`, `teams:[...]`, and `provenance: "direct"\|"team"\|"watch"` (the field the page actually filters/renders on). |
| `reviews.json` | Object keyed by PR URL; see § Review file format below for the full drafted-review shape `reviews_index.py` produces. |
| `nudges.json` | `{prs, posted, close_after}` when there's something to nudge about, or `null` — not collector-sourced; `null` is the accurate "nothing to show" shape, matching `build.py`'s own default when the file is absent. |
| `jira.json` | List of `{key, summary, status, priority, type, updated, project, due, labels}` — open issues assigned to the developer, written by `jira_fetch.sh`; empty (or absent) when `jira.host` isn't set or nothing has baked yet. |
| `calendar.json` | List of `{title, start, end, organizer, rsvp, url}` — upcoming events (next three days, primary calendar), written by the daily bake (`google_fetch.py`, or the refresher's full mode). |
| `gmail.json` | List of `{subject, from, when, kind, important, note}` — up to 6 unread inbox messages (metadata only) from `google_fetch.py`, or the refresher's condensed rows. The page has no Gmail panel; `brief.json`'s `mail` lines stay the readable summary. |
| `bake_stamp.json` | `{when}` — ISO-8601 instant of the last bake, written by `bake.sh` and by the refresher's full mode. When it is older than 24 h the page's brief area shows an amber "run the bake" banner. |
| `brief.json` | `{lines: [...≤5 one-line summaries...], mail: [...≤5 inbox summary lines...]}` — the daily bake's condensed status. |
| `requests.json` | List of every request the page has ever sent, in arrival order — see § Request contract below. |
| `quickwins.json` | `{generated_at, counts: {close, quick_win, stale, keep}, items: [...]}` — written by `ms-quickwins`, at most once a day. |
| `artifacts.json` | List of previously published artifact records (empty until a `publish` has happened). |
| `pending.json` | List of drafts awaiting the developer's approval; `build.py` inlines each item's file body from its `path` field (capped at 60 KiB) before handing it to the template. |
| `ms_usage.json` | List of per-agent token-usage log entries, written by `log_usage.py`; feeds the page's usage widget. |
| `master_usage.json` | `{current, history}` — the master session's own transcript-derived token cost; refreshed by `master_usage.py` on every handoff, `current` reset to `null` on a new session id. |
| `collected_at.txt` | Not JSON — a single ISO-8601 timestamp of the last full collection, shown in the page header. |

## Scheduled tokenless bake

The daily bake has two paths that write the same files:

- **Model path** — the `ms-refresher` agent in full mode (judgement: condensed Gmail rows,
  the brief).
- **Tokenless path** — `bake.sh`: `jira_fetch.sh` (pure curl) plus `google_fetch.py`
  (stdlib `urllib`; refreshes an OAuth access token from `google.clientFile` +
  `google.tokenFile`, then fetches Calendar v3 and Gmail metadata). No model, no MCP —
  safe to run headless on a schedule. A source with no credentials is skipped with a
  one-line notice; its files are left as is.

Both paths end by rewriting `bake_stamp.json` (`{when}`). `build.py` bakes the stamp into
`DATA.bake_stamp`; the template shows an amber "run the bake" banner in the brief area when
the stamp is older than 24 h. `google_auth_setup.py` is the one-time interactive consent
(loopback redirect flow) that creates `google.tokenFile` with a refresh token scoped to
`calendar.readonly` + `gmail.readonly`.

Scheduling is opt-in: when `bake.scheduledDaily` is `true`, `install.sh` installs
`io.mainstem.bake` (launchd, daily 08:30) or `mainstem-bake.timer` (systemd user timer)
from the templates in `service/`. The default is `false` — nothing is scheduled unless the
config says so.

## Request contract

The page's only write path is `POST /request`. `newReq(kind, text, targets, extra)` (in
`template.html`) builds `{id, when, kind, text, targets, status:"pending", reply:"", ...extra}`;
`postLocal` sends `{id, when, kind, text, targets, extra}` as the POST body. `ms_server.py`
rebuilds the record server-side (`rec = {...extra, id, kind, text, targets, extra, status:
"pending", created, when, reply:""}`), appends it to `requests.json`, and dispatches on `kind`:

- **Handled immediately, no model**: `jump`, `refresh`, `delete_worktrees`, `push_branches`,
  `open`, `rotate`, `edit_draft`, `publish`, and any `decision` whose `extra.decision` is
  `approve` / `approve_with_comments` / `request_changes` / `post_findings` (via
  `review_post.py`) or `defer` (handled inline). A stale-head posting decision is caught before
  it reaches `review_post.py` and auto-queues a `review_pr` re-review instead of failing silently.
- **Left `status: "pending"` for the master session**: `chat`, `decision` (`review_question`,
  `quickwins`), `review_pr`, and any `decision` `review_post.py` could not post safely.

The HTTP response is always the full, now-updated request record; the page polls
`GET /data/requests.json` for replies that arrive after the initial response (e.g. once the
master session picks up a pending one).

## Session `kind` classification

`collect.sh`'s `classify_kind(name, tty, host, tmux, env_kind)` decides `interactive` vs `agent`
vs `background` for each row in `sessions.json`:

1. If a launcher exported `MS_SESSION_KIND` for that pid (read from `/proc/<pid>/environ`,
   best-effort on macOS since it hides another process's environment there), trust it verbatim.
2. Else if the process name is one of the four agent scripts (`ms-executor`, `ms-quickwins`,
   `ms-refresher`, `ms-reviewer`), classify it `agent`.
3. Else if it has a tty or an ssh host, classify it `interactive`.
4. Otherwise, `background`.

## Review file format

Each `<reviewsDir>/active/<repo>-<pr>.md` file has YAML-like frontmatter (flat `key: value` lines)
followed by `## Section` headers: `Summary`, `Findings` (a table), `Inline comment drafts`
(`### F<n> — path:line` blocks: a mandatory `` ```excerpt start=<N> target=<N> [diff=1] `` fence —
`diff=1` means every row is unified-diff-marker-prefixed, present when the target sits inside the
PR's own diff; omitted when the reviewer fell back to plain head-file lines — followed by ≤2 STE
sentences of prose, then an optional `` ```suggestion `` block), `Questions`. `reviews_index.py`
turns these into `reviews.json`, one entry per PR URL, each draft carrying
`{id, loc, text, excerpt, file_url}` — `excerpt` is `{start, target, diff, code}` or `None`;
`file_url` deep-links to GitHub's Files-changed tab via `{pr_url}/files#diff-{sha256(path)}R{line}`.
`review_post.py` strips the excerpt fence before posting — GitHub already shows the code itself, the
fence is drawer-only evidence. `backfill_excerpts.py [--redo] [file.md ...]` regenerates excerpts
for review files written before this feature existed, or after a rewrite invalidates them.

## Publish (read-only render)

`ms_server.py`'s `publish` request kind calls `build.build(cfg, readonly=True)`, which bakes
`DATA.config.readonly = true` and writes to a separate file, `control-center-readonly.html`,
next to (never overwriting) the live `control-center.html` the local server serves. The template's
`body[data-readonly] [data-write]{display:none}` rule then hides every write-sending control.

The server itself never calls the Artifact tool — a stdlib HTTP server has no such capability, and
returning the full page HTML as the request's `reply` would get it persisted into `requests.json`
and re-embedded into every future build's data payload, growing without bound. So `do_publish`
writes the read-only HTML to `control-center-readonly.html` and returns only a short pointer (the
file path and its size) in the `reply`. The master Claude session that issued the `publish` request
reads that file from disk and is the one that actually calls `Artifact` to publish it, since only a
Claude session has that tool.

The LAN/Tailscale alternative documented in the README (`host`/`token`-gated, read-only GET) is
intentionally a documented, opt-in pattern only — it is not a built-in flag. `config.py` already
carries a `host` default (`127.0.0.1`) but no `token` field exists in the config schema or the
server's request handling. A contributor who wants this must wire the bind and the token check
themselves; nothing today silently half-implements it.
