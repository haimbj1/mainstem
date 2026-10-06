# Changelog

## 0.3.0

The shell release: the board looks and reads like a macOS app, and the assistant starts
doing board chores on request.

- macOS shell: navigation moves to a translucent left sidebar (vertical tabs with counts,
  master controls at the foot); slim toolbar; system font stack; near-black dark palette
  with hairline separators; zoom scales the content, never the chrome.
- One status per review row: a single colored pill says who acts — amber you, blue the
  author, green done, gray nothing — with the action in the phrase. The same headline tops
  every review card; the card leads with 3 summary lines and folds the rest into a
  collapsed notes-and-log; drafts start collapsed.
- Home becomes the inbox: a "Needs you" list leads (one line per item, across sources);
  the Decide-now queue collapses behind a chip.
- ✨ Assistant tips: a sidebar button runs a whole-board hygiene analysis (the quickwins
  pattern) into tips.json; tips render on Home as PROPOSED actions — tick what the
  assistant should do, "Run selected" executes only the picked items through the existing
  flows; arrival badges the button and toasts.
- The unread-replies chip names what it holds and offers mark-all-seen.
- New request kinds: board_tips, board_tips_exec.
- Fixes: refused posting clicks cannot hide a row; a decision hides a row only with its
  own landed receipt; whole-PR draft locations post to the review body; a partial draft
  match refuses instead of posting quietly.

## 0.2.0

The review loop release: the board now closes the loop between the offline reviews,
GitHub, and the developer — with as few clicks as possible.

- Pre-review staging: stage drafts as a GitHub PENDING review — inline with the code,
  visible only to you, nothing posted. Annotate a staged comment with `>>` lines to talk
  to the reviewer; "Reread pre-review" acts on every note, syncs your edits, and
  refreshes the staged copy. Staging all drafts is now the default after every review run.
- Auto-reassess: an author reply after a posted review queues the re-review on its own
  (once per reply, at most 3 per cycle); resolved findings get marked and the verdict moves.
- "⟲ Reassess" button on every review card for the manual case.
- Tokenless 5-minute reviews refresh: the server re-collects GitHub review state and an
  open page reloads itself when fresh data lands (never while you type or a drawer is open).
- Author replies and pushed fix rounds return a decided row to open work, with pills.
- Truthful row states: a decision hides a row only with that decision's own landed receipt;
  GitHub-approved PRs file under decided; an explicit "✓ approved" state filter.
- Resume for refused posting clicks: a stale-head refusal re-applies your decision to the
  drafts that survive the re-review, and bounces back only when the verdict flipped.
- Post buttons show `selected of total · N unticked`, so a partial post is never silent.
- Review posting hardening: whole-PR draft locations parse; a partial draft match refuses
  instead of posting quietly.
- Master lock: an flock on `<dataDir>/master.lock` makes the one-master check
  deterministic; `master_watch.py` replaces the ad-hoc watch loop.
- prune_reviews treats a PR that no longer resolves (re-created repo) as gone instead of
  failing the whole run.
- New config keys: `reviewsRefreshSeconds` (default 300, 0 disables).

## 0.1.2

- Scheduled tokenless bake: `bake.sh` runs `jira_fetch.sh` + the new `google_fetch.py`
  (stdlib-only Calendar/Gmail fetch via an OAuth refresh token) with no model involved;
  `google_auth_setup.py` does the one-time consent. Opt-in daily 08:30 scheduling via
  `bake.scheduledDaily` (launchd job or systemd user timer, wired by `install.sh`).
- New config keys: `google.clientFile`, `google.tokenFile`, `bake.scheduledDaily`.
- Staleness banner: every bake path writes `bake_stamp.json`; the brief area shows an
  amber "run the bake" warning when the stamp is older than 24 h.
- Session ledger: the collector records every session and keeps dead ones 14 days.
  A reboot no longer loses them — the Sessions panel lists ended sessions, and a PR row
  whose owner session died offers one-click restore (`claude --resume` in tmux).
- `preview.sh <branch> [port]`: run any branch against a snapshot of your real data
  before merging it.
- Atomic collector writes: an interrupted collect can no longer truncate a live data
  file; a corrupt file is named in the build error.
- Jump fix: a detached tmux session attaches in a new tab instead of hijacking a
  cwd-matching one.
- README quickstart is copy-pasteable; the repo ships its own one-entry marketplace
  (`/plugin marketplace add haimbj1/mainstem`).

## 0.1.1

- The skill starts the setup conversation automatically when no config exists — install the
  plugin, type /mainstem, done.
- CI: full fetch depth so gitleaks can diff pushed ranges.

## 0.1.0

Initial public release: server, collector, review pipeline, four agents, install/uninstall for
macOS and Linux, demo mode, doctor + setup onboarding, watched-repo review queue, inline review
code excerpts, session-kind labeling, read-only publish mode.
