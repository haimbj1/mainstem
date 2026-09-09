# mainstem — reference

Everything the local board does not need day to day: the collection agents, the
request semantics the master session answers, the ranking rules, and the optional artifact
publish. `SKILL.md` is the contract; this file is the detail behind it.

> Retired: Slack (2026-08-27) and the in-page live MCP reads (2026-08-30). The page now renders
> only what a collector baked into the configured `dataDir`'s `*.json`.

## Refresh — who does what

The master session **routes and publishes**. The work runs in subagents. The master no longer reads
an MCP payload: `ms-refresher` reads them and leaves small JSON behind.

| stage | who | what |
| --- | --- | --- |
| a | master | broadcast the session pings, merge the replies into `session_status.json` |
| b | `ms-refresher` | `collect.sh`, `reviews_index.py`, `session_status_from_notes.py`, and in `full` mode Jira · Calendar · Gmail · brief |
| c | master | `build.py`, `node --check`, publish |

### (a) Session pings — master only

Ask every other live Claude session what it is doing, so the board shows real work and not just
process state. Only the master can do this: the replies land in the master session.

- `ListAgents` → the live local interactive sessions (same names as `sessions.json`).
- `SendMessage` to each one **except this master session**, with exactly this text:
  ```
  MainStem sync from <master name>. Reply with ONE line, exactly this format, nothing else:
  STATUS | <repo or worktree> | <what you are doing now, ≤ 12 words> | <refs: PR #numbers, Jira keys, branch> | <blocked: none | reason>
  If you are idle with no active task, reply: STATUS | <cwd> | idle | - | none
  If you are holding a draft that needs the developer's approval before it goes out, add a SECOND line:
  PENDING | <ref: #<pr> or JIRA-KEY> | <what it is, ≤ 8 words> | <absolute path to the draft .md>
  ```
- **Do not wait on the replies.** Spawn `ms-refresher` (stage b) right away.
- Parse each reply as `STATUS | repo | doing | refs | blocked`. Split `refs` on commas or spaces,
  keep `#<n>`, your configured `jira.projects` prefixes and branch names, drop `-`. Trim `doing`
  to 12 words.
  Write the entry with `source: "ping"` and `when` = now.
- Parse a `PENDING | ref | what | path` line into `pending.json` (see "Pending approvals"). The
  session keeps the draft; this file is only the index the board renders.
- **Merge the pings into `session_status.json` after `ms-refresher` returns**, not before: the agent
  runs `session_status_from_notes.py`, which fills every un-pinged session from its handoff note.
  A ping entry always wins over a note entry. Read-modify-write, never truncate.
- A session with no ping and no note simply has no key — the board shows "no status" for it.
  A late reply lands on the next refresh. **Never block the refresh on replies.**

### (b) `ms-refresher` — the collection agent

```
Agent tool · subagent_type: "ms-refresher" · prompt: "mode: full"   (or "mode: cheap")
```

Pick the mode with the refresh policy below. The agent writes `worktrees.json`, `sessions.json`,
`session_notes.json`, `my_prs.json`, `review_requests.json`, `reviews.json`,
`session_status.json` (note fallback), and in `full` mode `jira.json`, `calendar.json`,
`gmail.json`, `brief.json` and `collected_at.txt`. It returns 8 lines or fewer: counts, the brief,
the PRs whose head moved, the PRs with no review file, and errors.

It cannot list Artifacts — a subagent has no Artifact tool. `artifacts.json` keeps its last value
until the master refreshes it itself (Artifact `action: "list"`, `scope: "all"`, limit 25; keep the
existing `note` per `url`, drop URLs that are gone).

Act on its report:

- **changed heads / no review file** → report them on the board only. The reviewer runs ONLY when the developer triggers it (✦ review buttons or an explicit ask) — never automatically; an auto re-review can silently burn tokens.
- **`quickwins.json` older than 24 h** → `ms-quickwins`.
- **errors** → say them in the reply; do not silently republish stale data.

### (c) Build and publish — master only

Two builds exist. Day to day, `build.py` (no flag) writes the write-enabled `control-center.html`
that the local server serves — that one is never published. A **publish** always uses the
**read-only** build instead:

1. `python3 build.py --readonly` → the configured `dataDir`'s `control-center-readonly.html`
   (written next to, never overwriting, `control-center.html`). This bakes
   `DATA.config.readonly = true`; the template's `body[data-readonly] [data-write]{display:none}`
   rule then hides every write-sending control, so the published page cannot send a request back.
   It also reads `pending.json` and inlines each item's draft file (`path` → `body`, capped at
   60 KB), because the published page has no filesystem. A missing file leaves the card with a
   header and no body — fix the path.
2. **Verify like this, and only like this:** extract the last `<script>` block from the read-only
   file and run `node --check` on it. Never launch a browser against the built page.
3. Publish — Artifact tool, the read-only file's path, favicon `🎛️`. URL is in `artifact_url.txt`.
   Pass the full manifest (only needed when it changed; omitting it keeps the stored one):

   ```json
   {
     "artifact": {},
     "mcp": { "servers": [
       { "server": "claude_ai_Atlassian",       "tools": ["searchJiraIssuesUsingJql"] },
       { "server": "claude_ai_Google_Calendar", "tools": ["list_events"] },
       { "server": "claude_ai_Gmail",           "tools": ["search_threads"] }
     ] }
   }
   ```

   Load the `artifact-capabilities` skill before a publish that changes the manifest — the control
   plane owns the valid server names and the entry shape, and it can differ from the four ids above.
   **Never share this page publicly.** The manifest bars it: a page that declares `mcp` is private
   or shared with named people only. That is the right posture anyway — the page carries the
   developer's PR, ticket and inbox state.

## The agents

| agent | model | what it does | why that model |
| --- | --- | --- | --- |
| `ms-refresher` | sonnet | collects everything, writes the JSON and the brief | scripted work plus small MCP reductions; no judgement |
| `ms-reviewer` | opus | reads PR diffs, writes the offline review files | real code review — the one place depth pays |
| `ms-quickwins` | opus | judges open tickets against code, PRs and notes | evidence and judgement across many sources |
| `ms-executor` | sonnet | runs the decisions the developer clicked | a fixed allow-list, no judgement |

Never call an agent for a `jump`. Never let an agent publish.



### Fallback when the agent type is not registered
A session started before `~/.claude/agents/*.md` existed does not know `subagent_type: "ms-refresher"` (registry is snapshotted at session start). Until the master is restarted, invoke the same definition through `general-purpose` with the matching `model` and this prompt: `Read ~/.claude/agents/<name>.md and follow its body exactly as your instructions (ignore the frontmatter). Task input: <input>.` Cost is identical.

## Refresh policy — which mode

`ms-refresher` takes one mode. Pick it like this:

1. **Default `cheap`** — every republish that answers a request (`chat`, `decision`,
   `review_question`). Scripts only, no MCP, about 15 s.
2. **`full`** when `collected_at.txt` is older than **1 hour**, or on the hour boundary of the
   auto-refresh loop.
3. A click on ↻ Refresh (`kind: refresh`) always runs `full`.

An answer must come back in seconds, but the board must never show stale PR state next to a fresh
reply.

## Auto-refresh — DISABLED (2026-08-30)

Do **not** run `/loop` or a cron that invokes `/mainstem` from the master. Measured cost: every fire re-injects this
entire skill file (~12k tokens) into the master's Fable context, plus 9 session pings and their replies, plus the
agent report — ~14% of the daily budget in two minutes when ticks queued up. Refresh only on an explicit ↻ click or
when the developer asks. If automation is wanted later, it must run OUTSIDE the master context (a cloud `/schedule` routine
that cannot see local sessions, or a shell cron that runs `collect.sh` + `build.py` without any model call) and the
master only publishes when the data hash changed.

## Resume after compaction or restart

Durable state lives on disk, not in the conversation: the data JSON, `requests.json`, `pending.json`, `session_status.json`, the configured `reviewsDir`, memory, and the handoff note. After a context compaction or a fresh master session:

1. Read the configured `masterHandoffNote` path (written by `handoff.sh` after every publish: artifact URL, cron id, open items, verbal asks).
2. `Artifact status` — if the watch is not connected, `Artifact read` once (this also re-arms it) and run `extract_requests.py`.
3. Do NOT re-create an auto-refresh cron (see Auto-refresh — disabled).
4. Continue with Step 0. Do not redo work the handoff says is done.

Keep the master small: never read MCP payloads or PR diffs in the master (agents do); never `Read` a built page; after every publish run `bash handoff.sh <cron-id> "<one-line verbal asks>"`.
Installed: the configured project's `settings.json` has a `PreCompact` hook (matcher `auto|manual`) that runs `handoff.sh` — so the note is fresh at the moment of any compaction, in master sessions only (project scope).

## Cost

The master routes and publishes. It does not read MCP payloads any more, and it does not read PR
diffs. That is the whole point of the split.

| agent | model | why |
| --- | --- | --- |
| `ms-refresher` | sonnet | scripted collection plus small `jq` reductions of MCP results |
| `ms-reviewer` | opus | reads full PR diffs and writes findings — judgement work |
| `ms-quickwins` | opus | weighs evidence across PRs, code, notes and memory |
| `ms-executor` | sonnet | a fixed allow-list of writes, no judgement |

Cheap by construction:

- a `cheap` refresh spawns one sonnet agent and returns 8 lines;
- `ms-reviewer` runs ONLY on the developer's explicit trigger (✦ buttons / their word), ≤ 6 PRs per call;
- `ms-quickwins` runs at most once a day;
- all four agents return a table or a short report, never a payload.

## Step 0 — pull requests the page sent (do this FIRST on every refresh)

### `kind: jump`
A Session / Go-to-session click (ms:// links cannot navigate inside the claude.ai sandbox). `extra.cc` is a `ms://session?...` or `ms://start?...` URL. Validate the `ms://` prefix and run `bash jump.sh "<cc>"` (runs the AppleScript directly via osascript; do NOT use `open ms://` — the URL-scheme app stalls on the Automation prompt). Handle a jump BEFORE any other work in the turn; it is latency-critical. Set status done, reply `opened`. A jump alone must not trigger a full refresh — republish only to record the reply.

The page can save new versions of itself with `DATA.requests` (the "Ask the master session" box and the worktree actions). This session is watching the artifact, so a save arrives as a republish notification.

1. `Artifact read` the URL → raw HTML (saved to a file when large).
2. `python3 extract_requests.py <that file>` → writes `requests.json`.
3. For each `status: "pending"` request, route it:

   | kind | who handles it |
   | --- | --- |
   | `jump` | **master**, first, before anything else. Never an agent. |
   | `chat` | **master** — it needs judgement and the conversation. Gather data if it needs any. |
   | `review_question` | **master** — answer `question` in `reply`, ≤ 3 sentences. No GitHub write. |
   | `refresh` | **master** — stage (a), `ms-refresher` in `full` mode, stage (c). Reply `Refreshed <HH:MM>`. |
   | `decision` | **`ms-executor`** — batch **all** pending decision objects into **one** call. |
   | `quickwins` | **`ms-quickwins`** — ignore the 24-hour rule; reply with the new counts. |
   | `delete_worktrees` | **`ms-executor`**, with `confirmed: true` — ask the developer first (below). |
   | `push_branches` | **master** — push each target that is ahead. |

   **Confirmations must be visible on the board.** The developer sometimes talks only to the page.
   When a board-originated request needs the developer's yes (any `gh pr review` verdict, a Jira close, a delete), do
   both at once: ask in the terminal (AskUserQuestion) AND set that request's `status` to
   `"needs_confirmation"` with the exact question in `reply`. The page renders Confirm/Deny buttons
   on such a request; a click posts a new request with `extra.confirms: <original id>` and
   `extra.confirmed: true|false`. Accept whichever channel answers first, ignore the loser, and
   write the outcome into the original request (`status: done`, `reply`: what happened).

   **Batching decisions.** Collect every pending `kind: decision` object into one array and send it
   as the `ms-executor` prompt. Before the call, set `"confirmed": true` on each object whose kind
   needs a confirmation — a Jira close, a review dismissal, `gh pr close`, a worktree delete, any
   `gh pr review` verdict — **after the developer says yes**. An object without the flag comes back as
   `NEEDS_CONFIRMATION` with the exact command: show the developer that command, and re-invoke `ms-executor`
   with only the confirmed objects. `ms-executor` writes `status` and `reply` into `requests.json`
   itself.

   **Worktree deletes.** Re-check `git status --porcelain` and `git log @{u}..` on each target and
   show the developer the dirty and unpushed ones before you set `confirmed`. `ms-executor` re-checks too and
   refuses a dirty or unpushed tree even when confirmed.

4. For a request the master handled itself, set `status: "done"` and write a short `reply` (≤ 3
   sentences, plain text) in `requests.json`. Then run stages (a)–(c) so the page shows the reply.

If the collector or a publish would overwrite a newer page version, `Artifact read` again first — the page is the source of truth for `requests`.

## Quick-win runner

Feeds the **Tickets** tab: every open Jira ticket on the developer, judged against the code, the PRs and the session
notes, so the ones that are already finished or already dead stop looking like work. The tab shows one row per
ticket; a verdict pill, an estimate and the verdict's buttons ride on the rows the runner flagged.

- **Input** — the open-Jira list in `jira.json` (`assignee = currentUser() AND statusCategory != Done`). Nothing else is in scope.
- **Verdicts** — one per ticket:
  - `close` — the work is done. The ticket is the only thing still open.
  - `quick_win` — one sitting finishes it (≤ 2 hours of real work).
  - `stale` — nobody is going to do this. Re-plan it or kill it.
  - `keep` — real, sized work. It gets no verdict pill and no verdict buttons; only its count reaches `counts.keep`.
- **Evidence rules** — every verdict carries `evidence`, and a `close` needs at least one **real ref**: a merged PR
  URL, or a `path:line` in a file (session note, memory file, source). "I remember" is not evidence. A grep that
  returns zero hits counts, if the command is in the `ref`. No ref → downgrade the verdict to `quick_win` or `keep`.
- **Output** — the configured `dataDir`'s `quickwins.json`:
  `{generated_at, counts:{close,quick_win,stale,keep}, items:[{key,summary,status,priority,verdict,confidence,reason,evidence:[{type,ref,text}],plan,estimate,action}]}`.
  `items` holds only `close`, `quick_win` and `stale`, ordered quick wins first, then stale. `estimate` is a short
  string (`15m`, `1h`, `2h`). `action` is one imperative line — it renders next to the `→` on the row.
- **How to run it** — the `ms-quickwins` agent (`subagent_type: "ms-quickwins"`, opus, read-only).
  Give it the open-Jira list from `jira.json` in the prompt. Run it at most once a day on a refresh:
  skip when `generated_at` is younger than 24 hours. A `kind: quickwins` request always runs it.
  The agent owns the whole contract; the outline below is what it holds, kept here for reference.

Prompt outline for the subagent:

- You judge open Jira tickets. Here is the list: `<key, summary, status, priority, updated, due>` for each.
- For each ticket, find out whether the work is already done, nearly done, or dead. Read, never write.
- Sources, in this order: `gh pr list` / `gh search prs` per key and per topic; the repos under the configured
  `workRoot` (grep for the symbols the ticket names); the configured `sessionNotesDir`'s `*.md`;
  your own `~/.claude/projects/<project>/memory/*.md`; the Jira description and comments.
- Assign one verdict: `close`, `quick_win`, `stale` or `keep`, plus `confidence` high / medium / low.
- A `close` needs a real ref (merged PR URL, or `path:line`). Without one, do not say `close`.
- `stale` needs the numbers: days since the last update, days past due, and the proof that no PR and no code mentions the key.
- Write `reason` (one sentence, why this verdict), `plan` (2–3 sentences, how to finish it — skip for `stale`),
  `estimate`, and `action` (one imperative line).
- Say what you could not check (a blocked command, a repo you could not read) inside the `action` or `reason` — never guess past it.
- Return only the JSON in the schema above. No prose.

## Review requests — offline reviews

Every PR that asks for the developer's review gets reviewed **before** they open the board, so a row on the page already
carries a verdict, the findings and ready-to-post comments.

- **Prompt** — `review-agent-prompt.md`. It is the whole contract:
  read-only GitHub (`gh pr view`, `gh pr diff`, `gh api` GETs), one file per PR, fixed frontmatter and sections.
- **Agents** — the `ms-reviewer` agent (`subagent_type: "ms-reviewer"`, opus). One call per repo
  group, drawn from your configured `github.orgs`, **≤ 6 PRs per call**, run
  in parallel. The prompt is the PR list only: `repo#number` and the URL for each. The agent holds
  the contract; `review-agent-prompt.md` stays as the reference copy.
- **Files** — the configured `reviewsDir`'s `active/<repo>-<pr>.md`. Never edit them by hand while agents run; they own the files.
- **What to re-run** — a PR whose `headRefOid` differs from `last_head_sha`, and a PR with no file at all. A PR whose
  head did not move needs no new run: the agent only refreshes `last_reviewed`.
- **Nudged PRs** — for every PR in `nudges.json`, check whether the author commented or pushed after `posted`.
  If yes, set `"replied": true` on that entry; the row then shows an "author replied" pill and the PR is alive again.
- **Index** — `reviews_index.py`, inside `ms-refresher`, turns the files into `reviews.json`. The page reads it: verdict pill, findings pill, and the
  inline review card with the drafts and the action strip.

### `kind: decision` from a review row

`item.id` is `review:<pr url>`, `item.src` is `review`, and the request carries `drafts` (the selected draft ids),
`review_path` (the .md file), and `question` or `why` where they apply. Posted text is the developer's own voice: first
person, STE, no AI attribution and no signature (the `pr-review-queue` skill rule). Read the drafts out of the .md
file, not out of the request. After a post, flip that finding's status in the .md from `📋 drafted` to `💬 posted`.

| decision | what you do |
| --- | --- |
| `approve` | **server-handled** (`review_post.py`) — the board click is the developer's confirmation; the server posts with zero model tokens. The master sees it only as a fallback. |
| `approve_with_comments` | **server-handled** — drafts read from the .md, lines validated against the diff, one APPROVE review. Master = fallback only. |
| `request_changes` | **server-handled** — same mechanics, REQUEST_CHANGES event. Master = fallback only. |
| `post_findings` | **server-handled** — COMMENT review, no verdict. Master = fallback only. |
| (fallback) | when `review_post.py` raises Unpostable (missing file, unparseable drafts), the request stays pending and the master posts it by hand — same rules the server follows: drafts from the .md, the developer's voice, stale-head guard, flip 📋→💬 after. |
| `review_question` | answer `question` in `reply`, ≤ 3 sentences. Read the PR or the diff if you must. **No GitHub write.** |
| `skip_review` | direct request → remove the developer as requested reviewer (`gh api -X DELETE .../requested_reviewers`). Team request → log only. Put `why` in the `reply`. |
| `close_stale` | the nudge comment got no answer: `gh pr close <url>` with a one-line STE comment that says why and that the author can reopen. **Confirm with the developer first.** |

## `kind: decision` — Do / Delegate / Drop / Defer / Close / Keep

Every queue row has a decision strip. A click sends one request; several clicks inside 4 seconds arrive as several
request objects in one publish. Extra fields: `decision`, `item {id, src, title, url, key?, cmd?}`, and `to` /
`why` / `until` / `note` depending on the decision. The page already marked the item done or snoozed locally —
your job is the outside-world effect.

| decision | Jira item (`item.key`) | GitHub review request / my PR | mail · calendar · worktree |
| --- | --- | --- | --- |
| `do` | transition to **In Progress** if the status is To Do or similar. No confirmation needed. | log only | log only |
| `delegate` | assign to `to` (`lookupJiraAccountId` first) and add a comment with `note` | `gh pr edit <item.url> --add-reviewer <to> --remove-reviewer <your-configured-login>`, then `gh pr comment` with `note` if present | draft the handoff text in `reply` — **never send it** |
| `drop` | transition to Done / Won't Do with `why` as a comment — **confirm with the developer first** | remove the developer as requested reviewer (`gh api -X DELETE .../requested_reviewers`) + comment `why` — **confirm with the developer first** | worktree → run the `delete_worktrees` flow (**confirm first**); others log only |
| `defer` | set `duedate = until`; comment `note` if present | log only | log only |
| `close` | transition to **Done** with a comment that links the evidence from `quickwins.json` — **confirm with the developer first**, same rule as any Jira close | n/a | n/a |
| `keep` | comment `note` only — no transition. The runner was wrong: drop the ticket from the quick wins on the next run (the `note` says what it missed). | n/a | n/a |

Decisions from a quick-win row on the Tickets tab carry `source: "quickwins"` and `item.id = "jira:<KEY>"`. `close` and `keep`
only ever come from there. Treat `do` from there like any other `do`, and `drop` on a `stale` row as **Won't Do**.

Confirmation rules:

- Confirm with the developer before the **first** Jira close and before the **first** review dismissal in a session. After they say yes, later ones of the same shape in that same session go through without asking again.
- Worktree deletion always follows the `delete_worktrees` rules (re-check dirty and unpushed, then ask).
- Everything else (transitions to In Progress, assignments, comments, due dates, reviewer swaps) runs without asking.

Always write `reply` (≤ 2 sentences: what you changed, or why you did nothing) and set `status: "done"`. The page
renders it in the **Decision log** section. If an effect fails, say so in `reply` — do not report success.

## Pending approvals (`pending.json`)

A session may draft text it must not post on its own — replies to a review, a Jira comment. It
holds the draft in a file and reports it on the **second** line of its status-ping reply:

```
PENDING | #42 | 7 replies to alex's review | <dataDir>/pending/repo-42-replies.md
```

The master session owns `pending.json` — sessions never write it:

```json
[{"id":"pend-42-replies","ref":"#42","url":"<pr url>","session":"<session name>",
  "what":"7 replies to alex's review","path":"<abs path to the draft .md>",
  "when":"<ISO when the session reported it>","status":"pending|approved|posted|rejected","reply":""}]
```

- `id` — stable slug; the page keeps its local decision under it (`cc:pend`).
- `url` — the PR (or ticket) the draft belongs to. The page puts a `pending approval · <what>` pill on every row
  with that URL, so the item is never invisible outside the Pending list on Home.
- `path` — the draft file. `build.py` reads it into `item.body` (capped at 60 KB) and the page renders it:
  `## N. <file:line>` → one numbered section with a checkbox and a Copy button, `Comment id: … — <url>` → a link,
  a `>` block before `Reply:` → the reviewer's words (muted), a `>` block after it → the reply that would go out.
- Drop the item from `pending.json` once it is posted or rejected — or set `status` and leave it for the record.

**Draft file shape** — a title line, whatever context lines the session wants, then one `## N. <where>` section per
thing to post. Each section: `Comment id: <id> — <url>`, the quoted original, `Reply:`, then the quoted reply.
Example: `<dataDir>/pending/repo-42-replies.md`.

### The three decisions the page sends

| decision | fields | what you do |
| --- | --- | --- |
| `approve_pending` | `pending_id`, `selected:[N…]`, `session` | `SendMessage` the owning session: "The developer approved replies `<N…>` on `<ref>`; post them." Nothing else — the session owns the posting and the file. When it confirms, set that item's `status` to `"posted"`. A section the developer unticked is **not** approved: name only the selected numbers. |
| `reject_pending` | `pending_id`, `why` | Relay `why` to the session verbatim. Set `status` to `"rejected"`. Nothing gets posted. |
| `pending_question` | `pending_id`, `question`, `session` | Relay the question, wait for the answer, put it in the request's `reply` (≤ 3 sentences). `status` stays `"pending"` — the developer still has to decide. |

Always write `reply` on the request and set it `done`, same as any other decision.

**Never ask the developer to approve a draft they cannot read.** A pending item must carry the draft text (via `path`), the link
to the thing it answers (`url`), and the jump to the session that wrote it (`session` must be a live session name).
An approval request without those three is a request to guess. Do not send it — fix the item instead.

## Jump-to-terminal (`ms://` links)

Session rows link to `ms://session?name=…&cwd=…&tmux=…&sid=…&tty=…`. A local jump app (source:
`claude-jump.applescript` here) handles the scheme: it finds the iTerm2 tab whose tty is in the
session's tty chain (or tmux name / title), selects it, else opens a new tab (`tmux attach` when the
session is in tmux). Rebuild after editing the script:
`osacompile -o <path to the jump app>.app claude-jump.applescript` then restore `Info.plist` URL
scheme `mc` and `lsregister -f`. First use needs the macOS Automation prompt (jump app → iTerm) accepted;
log at the configured jump-app log path (default `~/Library/Logs/mainstem-jump.log`).

Every PR, ticket, worktree and pending row also carries one **session button**:

- **Go to session · `<name>`** — a live session already owns the row: its status ping names the PR number, the Jira
  key or the branch, or it sits in the row's worktree. Same `ms://session?…` URL as the Sessions panel. When several
  sessions quote the same ref, the one whose cwd is the row's worktree wins.
- **Start session** — nobody owns it. `ms://start?cwd=<dir>&prompt=<text>`: the jump app opens a new iTerm2 tab,
  `cd`s there and runs `claude "<prompt>"`. `dir` is the worktree on the PR's head branch, else the repo's main clone
  under the configured `workRoot`, else the configured `workRoot` itself. The prompt is one line, ≤ 400 characters,
  and names the PR or ticket, the offline review path and where the session notes live — so the new session starts
  oriented.

## Ranking rules (in template.html)

Score 0–100 per item, higher = decide sooner.
- My PR: conflicts 88 · CI red 85 · changes requested 80 · approved 75 · no human review 45+6/day · draft 30.
- Review request (only DIRECT requests; team requests via your configured review team slug never enter the queue): 52 + 2.5/day since opened (cap 30); older than 45d → 38 "stale"; submodule bots 35; drafts −20.
- Jira: 35 + priority (Highest 35, High 25, Medium 10) + stuck 25 / review 15 / stale-in-progress 10; docs-project tickets −12 (epic carries them).
- Meeting (only ones the developer organizes) within 3h: 82 − 4/h. Important human mail: 50.
- Worktree with unpushed commits and no live session: 58. Dirty idle worktree: 22.

Change weights in `template.html`, not in the data.

## Notes

- Done / snoozed state is browser-local (localStorage). A rebuild does not reset it. `Do` / `Delegate` / `Drop` write `done`; `Defer` writes `snoozed` until the chosen date.
- Quick-win rows keep their own browser-local state in `cc:qw` (`{KEY: decision}`); a decided row hides until "Show decided" is on. It is per browser, so `quickwins.json` must drop the ticket once the outside-world effect is real.
- Pending approvals list one line per draft: ref, what, the session that wrote it, its age, then **Approve**
  (posts every drafted section) and **Open** (the draft body in the drawer, where sections can be unticked and
  Reject / Ask session live). They keep their own browser-local state in `cc:pend`
  (`{pending id: approve|reject|ask}`); a decided row dims. `pending.json` is the durable state, so update
  `status` there once the effect is real.
- Review rows keep their own browser-local state in `cc:rv` (`{pr url: decision}`); a decided row hides until "Show decided" is on. `reviews.json` and GitHub are the durable state.
- Every request whose `item.url` is the PR shows as a Thread at the bottom of that review card in the drawer — my text, then your `reply`. A reply not yet read gives the row a "new reply" pill; opening the card marks it read in `cc:seen`, per browser.
- **Layout — six tabs.** `Home · Reviews · Tickets · Sessions & work · Log · More`, one tab visible at a time.
  The active tab persists in `cc:tab` and is written to the URL hash: `#home #reviews #tickets #work #log #more`.
  `⇧1`…`⇧6` switch tabs; `r` toggles Reviews ⇄ Home. The old `#reviews` bookmark still lands on the Reviews tab
  and `#all` still means Home. Only the active tab's sections are *displayed* — the DOM keeps every section, so
  every render function and every live read still has its container.
  - **Home** — brief, a six-tile Now strip, the **top 10** of Decide now ("Show all N" opens the rest, persisted in
    `cc:qall`), and Pending approvals as one line per draft.
  - **Reviews** — the review list, the review-only Decision log and the ask box.
  - **Tickets** — one merged list: every Jira ticket, with the quick-win verdict pill, estimate and
    verdict-specific buttons on the rows the runner flagged. Chips: All / Quick wins / Stale / In progress /
    Review ready. "Re-run analysis" is unchanged.
  - **Sessions & work** — Efforts (with the selection bar and the worktree actions), Claude sessions, my PRs.
  - **Log** — the decision log and the request history, plus "Copy as standup".
  - **More** — calendar, mail, session notes, artifacts.
- **Detail opens in the right drawer** (`#drawer-right`, ~520 px, fixed, scrollable). It hosts the review cards,
  the pending draft bodies, the quick-win evidence and plan, and the queue row's `···` — the full Do / Delegate /
  Drop / Defer strip with the session button and the link. Nothing expands inline any more, so a list never grows
  under the pointer. `Esc` or a click outside closes it; opening it sets `data-drawer-open` on `<body>`.
- Queue rows are one line: title, the short reason, one primary button (`Do`, or `Review` on a review row) and
  `···`. At most two secondary pills stay on the row; everything else is in the drawer. `1`–`4` still decide on
  the selected row and open their form in the drawer. `/` filters the lists on the active tab.
- The decision log is `requests.json` filtered to `kind: "decision"` — it survives rebuilds, so it is the only durable record of what the developer decided.
- The MCP reads need an interactive session with the connectors; the collector alone works headless.
  `ms-refresher` runs them, not the master.
- A newly added `~/.claude/agents/*.md` may not reach a session that was already running when the
  file appeared. Restart the master session if `subagent_type: "ms-refresher"` is not found.
