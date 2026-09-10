#!/usr/bin/env python3
"""One-time interactive Google OAuth consent for the tokenless bake. Stdlib only.

Loopback redirect flow: opens the browser to Google's consent page, catches the
authorization code on a localhost port, exchanges it, and writes the refresh token
to the configured google.tokenFile. Scopes: calendar.readonly + gmail.readonly.

Prerequisite — an OAuth *desktop* client JSON at the configured google.clientFile.
Run once; after that google_fetch.py runs headless forever.
"""
import http.server
import json
import os
import secrets
import sys
import urllib.parse
import urllib.request
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import get, load_config  # noqa: E402

SCOPES = ("https://www.googleapis.com/auth/calendar.readonly "
          "https://www.googleapis.com/auth/gmail.readonly")

CLIENT_HOWTO = """\
No OAuth client file at {client_file}.

Create one (once) in the Google Cloud Console:
  1. https://console.cloud.google.com/ — pick or create a project.
  2. APIs & Services > Library — enable "Google Calendar API" and "Gmail API".
  3. APIs & Services > OAuth consent screen — External, add your own account
     as a test user (Testing status is enough; only you use this client).
  4. APIs & Services > Credentials — Create credentials > OAuth client ID >
     Application type "Desktop app".
  5. Download the client JSON and save it to {client_file}
     (or point google.clientFile in your config somewhere else).

Then rerun this script."""


class _CodeCatcher(http.server.BaseHTTPRequestHandler):
    result = {}

    def do_GET(self):  # noqa: N802 — http.server API
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _CodeCatcher.result = {k: v[0] for k, v in qs.items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<p>mainstem: consent received &mdash; you can close this tab.</p>")

    def log_message(self, *_):
        pass


def main():
    cfg = load_config()
    client_file = os.path.expanduser(get(cfg, "google.clientFile"))
    token_file = os.path.expanduser(get(cfg, "google.tokenFile"))
    if not os.path.isfile(client_file):
        print(CLIENT_HOWTO.format(client_file=client_file), file=sys.stderr)
        return 1
    with open(client_file) as f:
        client = json.load(f)
    client = client.get("installed") or client.get("web") or client

    server = http.server.HTTPServer(("127.0.0.1", 0), _CodeCatcher)
    redirect_uri = f"http://127.0.0.1:{server.server_port}"
    state = secrets.token_urlsafe(16)
    auth_url = client.get("auth_uri", "https://accounts.google.com/o/oauth2/v2/auth") + "?" + \
        urllib.parse.urlencode({
            "client_id": client["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",  # required to get a refresh token
            "prompt": "consent",       # required to get one again on re-consent
            "state": state,
        })
    print("Opening the browser for consent. If nothing opens, visit:\n\n" + auth_url + "\n")
    webbrowser.open(auth_url)
    print(f"Waiting for the redirect on {redirect_uri} ...")
    server.handle_request()
    server.server_close()

    result = _CodeCatcher.result
    if result.get("error"):
        raise SystemExit(f"google_auth_setup: consent refused: {result['error']}")
    if result.get("state") != state:
        raise SystemExit("google_auth_setup: state mismatch on the redirect — try again")
    if "code" not in result:
        raise SystemExit("google_auth_setup: redirect carried no code — try again")

    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "code": result["code"],
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "redirect_uri": redirect_uri,
    }).encode()
    token_uri = client.get("token_uri", "https://oauth2.googleapis.com/token")
    with urllib.request.urlopen(urllib.request.Request(token_uri, data=body), timeout=30) as resp:
        token = json.load(resp)
    if "refresh_token" not in token:
        raise SystemExit("google_auth_setup: Google returned no refresh_token — revoke the app's "
                         "access under your Google account's security settings and rerun")

    os.makedirs(os.path.dirname(token_file), exist_ok=True)
    tmp = f"{token_file}.tmp.{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"refresh_token": token["refresh_token"], "scopes": SCOPES.split()}, f, indent=1)
    os.replace(tmp, token_file)
    print(f"wrote {token_file} — google_fetch.py (and the daily bake) can now run headless")
    return 0


if __name__ == "__main__":
    sys.exit(main())
