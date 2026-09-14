# Changelog

## Unreleased

- Scheduled tokenless bake: `bake.sh` runs `jira_fetch.sh` + the new `google_fetch.py`
  (stdlib-only Calendar/Gmail fetch via an OAuth refresh token) with no model involved;
  `google_auth_setup.py` does the one-time consent. Opt-in daily 08:30 scheduling via
  `bake.scheduledDaily` (launchd job or systemd user timer, wired by `install.sh`).
- New config keys: `google.clientFile`, `google.tokenFile`, `bake.scheduledDaily`.
- Staleness banner: every bake path writes `bake_stamp.json`; the brief area shows an
  amber "run the bake" warning when the stamp is older than 24 h.

## 0.1.1

- The skill starts the setup conversation automatically when no config exists — install the
  plugin, type /mainstem, done.
- CI: full fetch depth so gitleaks can diff pushed ranges.

## 0.1.0

Initial public release: server, collector, review pipeline, four agents, install/uninstall for
macOS and Linux, demo mode, doctor + setup onboarding, watched-repo review queue, inline review
code excerpts, session-kind labeling, read-only publish mode.
