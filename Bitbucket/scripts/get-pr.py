#!/usr/bin/env python3
"""
Fetches pull request metadata for a Bitbucket PR.

Usage:
    python3 get-pr.py <pr_number>

Output (JSON):
    {
      "number": 123,
      "title": "...",
      "description": "...",
      "headRefName": "feature/my-branch",
      "baseRefName": "main",
      "headSha": "abc123...",
      "files": [{"path": "src/foo.ts", "status": "modified"}, ...]
    }

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
        elif e.code == 404:
            print(f"PR not found.", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <pr_number>", file=sys.stderr)
        sys.exit(1)

    pr_number = sys.argv[1]

    user = os.environ.get("BITBUCKET_USER")
    token = os.environ.get("BITBUCKET_TOKEN")
    if not user or not token:
        print("Error: BITBUCKET_USER and BITBUCKET_TOKEN must be set.", file=sys.stderr)
        print("Run python3 scripts/setup.py and fill in .claude/settings.local.json", file=sys.stderr)
        sys.exit(1)

    remote_url = get_remote_url()
    workspace, repo = parse_bitbucket_url(remote_url)

    base = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo}/pullrequests/{pr_number}"

    pr = api_get(base, user, token)
    diffstat = api_get(f"{base}/diffstat", user, token)

    files = []
    for entry in diffstat.get("values", []):
        # Each entry has 'status' (added, modified, removed, renamed) and 'new'/'old' with path
        status = entry.get("status", "modified")
        path = (entry.get("new") or entry.get("old") or {}).get("path", "")
        if path:
            files.append({"path": path, "status": status})

    result = {
        "number": pr["id"],
        "title": pr["title"],
        "description": pr.get("description", ""),
        "headRefName": pr["source"]["branch"]["name"],
        "baseRefName": pr["destination"]["branch"]["name"],
        "headSha": pr["source"]["commit"]["hash"],
        "files": files,
    }

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
