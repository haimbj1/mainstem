#!/usr/bin/env python3
"""Shared config resolver for mainstem. Priority, highest to lowest:
$MS_CONFIG > ~/.config/mainstem/config.json > <repo>/config.local.json > built-in DEFAULTS.
Missing files are skipped. Fields merge shallowly per top-level key, except nested config
objects ('github', 'jira', 'modules', 'google', 'bake'), which deep-merge one level down."""
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

DEFAULTS = {
    "brand": "MainStem",
    "workRoot": "~/work",
    "host": "127.0.0.1",
    "port": 7777,
    "github": {"login": "", "orgs": []},
    "jira": {"host": "", "email": "", "projects": []},
    "google": {
        "clientFile": "~/.config/mainstem/google_client.json",
        "tokenFile": "~/.config/mainstem/google_token.json",
    },
    "reviews": {"watchRepos": []},
    "bake": {"scheduledDaily": False},
    "dataDir": "~/.local/share/mainstem",
    "reviewsDir": "~/.claude/reviews",
    "sessionNotesDir": "~/.claude/sessions",
    "masterHandoffNote": "~/.claude/sessions/master-mainstem.md",
    "masterTmuxSession": "ms-master",
    "rebuildIntervalSeconds": 1800,
    "noteRecollectThrottleSeconds": 30,
    "modules": {
        "jira": False, "calendar": False, "mail": False,
        "quickwins": False, "reviews": True, "jump": True,
    },
}

PATH_KEYS = {"workRoot", "dataDir", "reviewsDir", "sessionNotesDir", "masterHandoffNote"}


def _layer_paths():
    # Listed lowest-to-highest priority: load_config() merges each layer on top of the
    # previous one, so the LAST path here wins. $MS_CONFIG is the most specific override
    # (a one-off file for a single run) and must beat the user's standing config.
    paths = [
        os.path.join(REPO_ROOT, "config.local.json"),
        os.path.expanduser("~/.config/mainstem/config.json"),
    ]
    if os.environ.get("MS_CONFIG"):
        paths.append(os.environ["MS_CONFIG"])
    return paths


def _deep_merge(base, override):
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config():
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy
    for p in _layer_paths():
        if p and os.path.isfile(p):
            with open(p) as f:
                cfg = _deep_merge(cfg, json.load(f))
    for k in PATH_KEYS:
        if isinstance(cfg.get(k), str):
            cfg[k] = os.path.abspath(os.path.expanduser(cfg[k]))
    return cfg


def get(cfg, dotted_path, default=None):
    node = cfg
    for part in dotted_path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def _main(argv):
    cfg = load_config()
    if len(argv) >= 1 and argv[0] == "dump":
        print(json.dumps(cfg, indent=2))
        return 0
    if len(argv) >= 2 and argv[0] in ("get", "path"):
        val = get(cfg, argv[1])
        if val is None:
            return 1
        if argv[0] == "path" and isinstance(val, str):
            print(os.path.abspath(os.path.expanduser(val)))
        elif isinstance(val, (dict, list)):
            print(json.dumps(val))
        else:
            print(val if not isinstance(val, bool) else str(val).lower())
        return 0
    print("usage: config.py {dump|get <dotted.path>|path <dotted.path>}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
