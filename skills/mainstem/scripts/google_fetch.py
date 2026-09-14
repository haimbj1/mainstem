#!/usr/bin/env python3
"""Tokenless Google bake — no model, stdlib urllib only.

Refreshes an OAuth access token (client id/secret + refresh token, both from local
files), then writes to the configured dataDir:

- calendar.json — the next 3 days of events from the primary calendar,
  [{title, start, end, organizer, rsvp, url}] (the shape the page renders);
- gmail.json — up to 6 unread inbox messages, metadata only (From, Subject, date),
  [{subject, from, when, kind, important, note}].

Writes are atomic (tmp + os.replace). Missing credential files print a one-line
notice and leave both files as is (exit 0) — run google_auth_setup.py once to
create the token file. A present-but-broken credential or an HTTP failure is an
error and exits non-zero.
"""
import datetime
import email.utils
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import get, load_config  # noqa: E402

CALENDAR_DAYS = 3
GMAIL_MAX = 6
TIMEOUT = 30


def _http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        body = e.read()[:300].decode("utf-8", "replace")
        raise SystemExit(f"google_fetch: HTTP {e.code} on {url.split('?')[0]}: {body}")


def _atomic_write(path, payload):
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=1)
    os.replace(tmp, path)


def refresh_access_token(client_file, token_file):
    with open(client_file) as f:
        client = json.load(f)
    client = client.get("installed") or client.get("web") or client
    token = json.load(open(token_file))
    if "refresh_token" not in token:
        raise SystemExit(f"google_fetch: {token_file} has no refresh_token — rerun google_auth_setup.py")
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": token["refresh_token"],
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
    }).encode()
    resp = _http(client.get("token_uri", "https://oauth2.googleapis.com/token"), data=body)
    return resp["access_token"]


def fetch_calendar(auth):
    now = datetime.datetime.now(datetime.timezone.utc)
    q = urllib.parse.urlencode({
        "timeMin": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timeMax": (now + datetime.timedelta(days=CALENDAR_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "50",
    })
    data = _http(f"https://www.googleapis.com/calendar/v3/calendars/primary/events?{q}", headers=auth)
    rows = []
    for ev in data.get("items", []):
        rsvp = next((a.get("responseStatus") for a in ev.get("attendees", []) if a.get("self")),
                    "accepted")
        rows.append({
            "title": ev.get("summary") or "(no title)",
            "start": (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date"),
            "end": (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date"),
            "organizer": (ev.get("organizer") or {}).get("email") or "",
            "rsvp": rsvp,
            "url": ev.get("hangoutLink") or ev.get("htmlLink") or "",
        })
    return rows


def fetch_gmail(auth):
    q = urllib.parse.urlencode({"q": "in:inbox is:unread", "maxResults": str(GMAIL_MAX)})
    listing = _http(f"https://gmail.googleapis.com/gmail/v1/users/me/messages?{q}", headers=auth)
    rows = []
    for ref in listing.get("messages", []):
        mq = urllib.parse.urlencode(
            [("format", "metadata")] + [("metadataHeaders", h) for h in ("From", "Subject", "Date")])
        msg = _http(f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{ref['id']}?{mq}",
                    headers=auth)
        hdrs = {h["name"].lower(): h["value"]
                for h in (msg.get("payload") or {}).get("headers", [])}
        sender_name, sender_addr = email.utils.parseaddr(hdrs.get("from", ""))
        when = None
        if hdrs.get("date"):
            try:
                when = email.utils.parsedate_to_datetime(hdrs["date"]).isoformat()
            except ValueError:
                when = None
        rows.append({
            "subject": hdrs.get("subject") or "(no subject)",
            "from": sender_name or sender_addr,
            "when": when,
            # No model in this path, so classification is mechanical: GitHub
            # notification mail is the one kind the page filters out of the queue.
            "kind": "github" if "github" in sender_addr.lower() else "human",
            "important": True,
            "note": None,
        })
    return rows


def main():
    cfg = load_config()
    data_dir = cfg["dataDir"]
    client_file = os.path.expanduser(get(cfg, "google.clientFile"))
    token_file = os.path.expanduser(get(cfg, "google.tokenFile"))
    if not (os.path.isfile(client_file) and os.path.isfile(token_file)):
        print("google_fetch: no OAuth client/token file (run google_auth_setup.py) — "
              "calendar.json and gmail.json left as is")
        return 0
    auth = {"Authorization": f"Bearer {refresh_access_token(client_file, token_file)}"}
    events = fetch_calendar(auth)
    mail = fetch_gmail(auth)
    _atomic_write(os.path.join(data_dir, "calendar.json"), events)
    _atomic_write(os.path.join(data_dir, "gmail.json"), mail)
    print(f"google: {len(events)} events · {len(mail)} unread messages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
