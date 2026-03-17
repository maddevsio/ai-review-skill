#!/usr/bin/env python3
"""
Posts a PR summary as a general Bitbucket comment and submits a verdict.

Usage:
    python3 post-summary.py <pr_number> <summary_file> <event>

    event: APPROVE | REQUEST_CHANGES | COMMENT

Requires environment variables:
    BITBUCKET_USER  — Bitbucket account email
    BITBUCKET_TOKEN — App Password
"""

import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Optional


def api_request(method: str, url: str, user: str, token: str, body: Optional[dict] = None) -> dict:
    auth = base64.b64encode(f"{user}:{token}".encode()).decode()
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if data else {}),
        },
    )
    try:
        with urllib.request.urlopen(req) as response:
            raw = response.read()
            if not raw:
                return {}
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        print(f"Error: HTTP {e.code} — {e.reason}", file=sys.stderr)
        print(body_text, file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def get_remote_url() -> str:
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Error: could not get git remote URL.", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def parse_bitbucket_url(url: str) -> tuple[str, str]:
    patterns = [
        r"https?://(?:[^@]+@)?bitbucket\.org/([^/]+)/([^/]+?)(?:\.git)?$",
        r"git@bitbucket\.org:([^/]+)/([^/]+?)(?:\.git)?$",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1), match.group(2)
    print(f"Error: remote URL does not look like a Bitbucket URL: {url}", file=sys.stderr)
    sys.exit(1)


VALID_EVENTS = {"APPROVE", "REQUEST_CHANGES", "COMMENT"}


def main() -> None:
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <pr_number> <summary_file> <event>", file=sys.stderr)
        print(f"  event: {' | '.join(sorted(VALID_EVENTS))}", file=sys.stderr)
        sys.exit(1)

    pr_number, summary_file, event = sys.argv[1], sys.argv[2], sys.argv[3]

    if event not in VALID_EVENTS:
        print(f"Error: invalid event {event!r}. Must be one of: {', '.join(sorted(VALID_EVENTS))}", file=sys.stderr)
        sys.exit(1)

    user = os.environ.get("BITBUCKET_USER")
    token = os.environ.get("BITBUCKET_TOKEN")
    if not user or not token:
        print("Error: BITBUCKET_USER and BITBUCKET_TOKEN must be set.", file=sys.stderr)
        sys.exit(1)

    with open(summary_file) as f:
        summary = f.read().strip()

    workspace, repo = parse_bitbucket_url(get_remote_url())
    base = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo}/pullrequests/{pr_number}"

    # Post summary as a general comment (no inline field)
    api_request("POST", f"{base}/comments", user, token, {"content": {"raw": summary}})
    print("Summary posted as general comment.")

    if event == "APPROVE":
        api_request("POST", f"{base}/approve", user, token)
        print("PR approved.")
    elif event == "REQUEST_CHANGES":
        api_request("POST", f"{base}/request-changes", user, token)
        print("Changes requested.")


if __name__ == "__main__":
    main()
