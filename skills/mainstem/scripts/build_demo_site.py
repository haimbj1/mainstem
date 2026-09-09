#!/usr/bin/env python3
"""Bake the demo board as a static site (for GitHub Pages, or any static host).

Seeds the fake dataset into a temp dataDir, builds the page in read-only mode (request
controls hidden — same branch the phone-publish path uses), wraps it with the same
document shell the server serves, and writes <out_dir>/index.html.

The config here is deliberately fictional and built inline — never load_config() — so a
run on a machine with a real user config can never bake personal values into a page
meant for publishing. Usage: build_demo_site.py [out_dir]  (default: _site)
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build as build_mod  # noqa: E402
import demo_seed  # noqa: E402
from ms_server import DOCTYPE  # noqa: E402


def demo_config(data_dir):
    return {
        "brand": "MainStem",
        "workRoot": data_dir,
        "host": "127.0.0.1",
        "port": 7787,
        "github": {"login": "demo-dev", "orgs": ["acme-corp"]},
        "jira": {"host": "", "email": "", "projects": ["DEMO"]},
        "reviews": {"watchRepos": []},
        "dataDir": data_dir,
        "reviewsDir": os.path.join(data_dir, "reviews"),
        "sessionNotesDir": os.path.join(data_dir, "notes"),
        "masterHandoffNote": os.path.join(data_dir, "master.md"),
        "modules": {m: True for m in ("jira", "calendar", "mail", "quickwins", "reviews", "jump")},
    }


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "_site"
    data_dir = tempfile.mkdtemp(prefix="ms-demo-site-")
    demo_seed.write_demo_data(data_dir)
    cfg = demo_config(data_dir)
    built = build_mod.build(cfg, readonly=True)
    os.makedirs(out_dir, exist_ok=True)
    with open(built) as f:
        body = f.read()
    with open(os.path.join(out_dir, "index.html"), "w") as f:
        f.write(DOCTYPE + body + "</html>")
    shutil.rmtree(data_dir)
    print("demo site: %s/index.html" % out_dir)


if __name__ == "__main__":
    main()
