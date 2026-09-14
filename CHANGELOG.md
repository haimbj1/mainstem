# Changelog

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
