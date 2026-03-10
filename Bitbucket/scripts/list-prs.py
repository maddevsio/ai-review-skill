#!/usr/bin/env python3
"""
Lists open pull requests for the current Bitbucket repository.

Usage:
    python3 list-prs.py

Output: table of open PRs (number, title, author, branch).

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
import urllib.parse
import urllib.request


def get_remote_url() -> str:
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Error: could not get git remote URL. Are you in a git repo?", file=sys.stderr)
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


def api_get(url: str, user: str, token: str) -> dict:
    auth = base64.b64encode(f"{user}:{token}".encode()).decode()
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"Error: HTTP {e.code} — {e.reason}", file=sys.stderr)
        if e.code == 401:
            print("Check your BITBUCKET_USER and BITBUCKET_TOKEN.", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    user = os.environ.get("BITBUCKET_USER")
    token = os.environ.get("BITBUCKET_TOKEN")
    if not user or not token:
        print("Error: BITBUCKET_USER and BITBUCKET_TOKEN must be set.", file=sys.stderr)
        print("Run python3 scripts/setup.py and fill in .claude/settings.local.json", file=sys.stderr)
        sys.exit(1)

    remote_url = get_remote_url()
    workspace, repo = parse_bitbucket_url(remote_url)

    params = urllib.parse.urlencode({"state": "OPEN", "pagelen": 50})
    api_url = (
        f"https://api.bitbucket.org/2.0/repositories"
        f"/{workspace}/{repo}/pullrequests?{params}"
    )

    data = api_get(api_url, user, token)
    prs = data.get("values", [])

    if not prs:
        print("No open pull requests found.")
        return

    print(f"{'#':<6} {'Title':<50} {'Author':<20} {'Branch'}")
    print("-" * 100)
    for pr in prs:
        number = pr["id"]
        title = pr["title"][:49]
        author = pr["author"].get("display_name", pr["author"].get("nickname", "unknown"))[:19]
        branch = pr["source"]["branch"]["name"]
        print(f"{number:<6} {title:<50} {author:<20} {branch}")


if __name__ == "__main__":
    main()
