# MainStem

A local, config-driven dashboard for your git worktrees, Claude Code sessions, and GitHub
review queue. Everything runs on your machine — no accounts, no telemetry. A local Python
server collects your git/GitHub/Jira state, bakes it into one static HTML page, and serves it
at `127.0.0.1:7777`; a handful of Claude Code agents fill in the parts that need judgement
(drafted PR reviews, Jira quick-win verdicts, decision execution).

## Screenshot

**[▶ Live demo](https://haimbj1.github.io/mainstem/)** — the board with fictional data, no install needed.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://haimbj1.github.io/mainstem/screenshot-dark.png">
  <img alt="MainStem, demo mode" src="https://haimbj1.github.io/mainstem/screenshot-light.png">
</picture>


## Quickstart

### Option A — plugin install

If you use Claude Code plugins:

```
/plugin marketplace add <marketplace-org>/<marketplace-repo>
/plugin install mainstem
```

The plugin ships the skill and the four `ms-*` agents (`.claude-plugin/plugin.json`). Then run
the skill's own onboarding conversation:

```
/mainstem setup
```

It runs a doctor pass (checks `git`, `gh`, `jq`, `python3`, `node`, optionally `tmux`/iTerm2),
interviews you for `workRoot`, GitHub login/orgs, Jira host/projects, which modules to enable,
and the port, writes `~/.config/mainstem/config.json`, and starts the server.

### Option B — standalone install

```bash
git clone <this-repo> mainstem
cd mainstem
./install.sh
```

`install.sh` runs `ms_doctor.sh` first and refuses to continue if a *required* tool is
missing (it prints the exact `brew install ...` fix). It then symlinks the skill and agents
into `~/.claude/skills` and `~/.claude/agents`, writes a default `config.example.json` copy to
`~/.config/mainstem/config.json` if none exists, installs the launchd job (macOS) or
systemd user unit (Linux), starts it, and prints the URL once `/health` answers. `uninstall.sh`
reverses the service and the symlinks; your config and `dataDir` are left untouched.

Either way, open `http://127.0.0.1:7777` (or your configured port) once the server is up.

## Config reference

MainStem reads one merged JSON config — see `config.example.json` for a starting point,
and `docs/architecture.md` for the exact file-resolution order and merge rules. Fields:

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `brand` | string | `"MainStem"` | Display name shown in the page header. |
| `workRoot` | path | `~/work` | Directory of git repos/worktrees to scan. |
| `host` | string | `127.0.0.1` | Bind address. Set to a Tailscale/LAN address only if you want the remote-read mode below — see Security posture. |
| `port` | number | `7777` | Local server port. |
| `github.login` | string | `""` | GitHub username; falls back to `gh api user -q .login` when empty. |
| `github.orgs` | array | `[]` | GitHub orgs whose PRs and review requests to collect. |
| `jira.host` | string | `""` | Jira Cloud host, e.g. `yourteam.atlassian.net`. Empty disables Jira entirely. |
| `jira.email` | string | `""` | Jira account email, paired with an API token for `jira_fetch.sh`. |
| `jira.projects` | array | `[]` | Jira project keys to filter to. An empty list disables ticket parsing even if `jira.host` is set. |
| `reviews.watchRepos` | array | `[]` | Extra repos whose open PRs feed the review queue even without a direct or team review request (shown with `provenance: "watch"`). |
| `dataDir` | path | `~/.local/share/mainstem` | Where collected JSON and the built page live. |
| `reviewsDir` | path | `~/.claude/reviews` | Root of drafted-review `.md` files (an `active/` subdirectory). |
| `sessionNotesDir` | path | `~/.claude/sessions` | Root of session handoff notes. |
| `masterHandoffNote` | path | `~/.claude/sessions/master-mainstem.md` | The one file a rotated master session reads on startup. |
| `masterTmuxSession` | string | `"ms-master"` | tmux session name the page's Rotate-master button launches or respawns. |
| `rebuildIntervalSeconds` | number | `1800` | How often the server re-collects and rebuilds on its own. |
| `noteRecollectThrottleSeconds` | number | `30` | Minimum gap between session-note-triggered recollects on page load. |
| `modules.jira` | bool | `false` | Show the Jira tab (needs a daily bake — see `docs/architecture.md`). |
| `modules.calendar` | bool | `false` | Show the calendar section (needs a daily bake). |
| `modules.mail` | bool | `false` | Show the mail summary line (needs a daily bake). |
| `modules.quickwins` | bool | `false` | Show quick-win verdicts on Jira tickets. |
| `modules.reviews` | bool | `true` | Show the PR review queue and drafted-review drawer. |
| `modules.jump` | bool | `true` | Show the jump-to-session button (macOS + iTerm2 only). |

Every field above ships in `config.example.json` with its real default value. Override any of
them via `~/.config/mainstem/config.json`, `<repo>/config.local.json`, or `$MS_CONFIG`.

## Platform notes

- **macOS is first-class**: `install.sh` installs a launchd job; the jump-to-session button
  (`modules.jump`) drives iTerm2 via AppleScript; `render_check.sh`'s screenshot helper expects
  Chrome at its default macOS install path.
- **Linux is degraded, not unsupported**: `install.sh` installs a systemd user unit instead of
  launchd; jump-to-session (`modules.jump`) has no iTerm2 equivalent and stays off; everything
  else — server, collectors, reviews, sessions panel, publish — works the same.

## Security posture

The server binds to `127.0.0.1` by default and only that. Nothing leaves your machine unless
you explicitly:

- ask a Claude session to **publish** a read-only snapshot as a Claude artifact, or
- opt into the **LAN/Tailscale read-only mode** documented below by setting `host` yourself.

`POST /request` (the only way to trigger a write — jump, refresh, delete a worktree, push a
branch, post a review) always refuses non-loopback callers, with no exception, even when the
LAN mode is enabled for reads. There is no telemetry, no analytics, and no outbound network call
except the ones you've already configured yourself (`gh`, `jira_fetch.sh`).

## Phone / remote read

Two ways to check the board from your phone:

1. **Publish** (recommended): ask your Claude session to publish the board — it renders a
   read-only snapshot (every action button hidden) as a private Claude artifact, viewable from
   any device.
2. **LAN/Tailscale** (advanced, off by default, documented pattern rather than a built-in flag
   today): set `host` in your config to your Tailscale or LAN address to bind there instead of
   `127.0.0.1`. A read-only `?token=` check on every GET is the intended gate for this mode but
   isn't implemented yet — `token` isn't a config field, and nothing enforces it — so until it
   lands, changing `host` alone exposes reads to anyone who can reach that address, with no token
   gate. `POST /request` already always refuses non-loopback callers, no exceptions — writes only
   ever happen from the machine running the server, and that part holds today. This mode must
   never be exposed to the open internet, and is not a public tunnel.

## More docs

- `docs/architecture.md` — config resolution, every data file's shape, the request contract,
  session-kind classification, the review file format, and the read-only publish hand-off.
- `CONTRIBUTING.md` — running demo mode and CI checks locally.
- `docs/PUBLISH.md` — the manual pre-publish audit runbook (owner-only, never automated).
- `CHANGELOG.md` — release notes.
