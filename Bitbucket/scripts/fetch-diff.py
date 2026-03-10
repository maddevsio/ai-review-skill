#!/usr/bin/env python3
"""
Fetches the raw diff for a Bitbucket pull request.

Writes the raw diff to /tmp/pr-diff-raw-<pr_number>.txt.
Run annotate-diff.py <pr_number> afterwards to produce the annotated diff.

Usage:
    python3 fetch-diff.py <pr_number>

Requires environment variables:
    BITBUCKET_USER  — Bitbucket account email
    BITBUCKET_TOKEN — App Password
"""

import base64
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

    api_url = (
        f"https://api.bitbucket.org/2.0/repositories"
        f"/{workspace}/{repo}/pullrequests/{pr_number}/diff"
    )

    auth = base64.b64encode(f"{user}:{token}".encode()).decode()
    req = urllib.request.Request(
        api_url,
        headers={
            "Authorization": f"Basic {auth}",
            "Accept": "text/plain",
        },
    )

    out_path = f"/tmp/pr-diff-raw-{pr_number}.txt"

    try:
        with urllib.request.urlopen(req) as response:
            with open(out_path, "w") as f:
                f.write(response.read().decode("utf-8"))
        print(f"Raw diff written to {out_path}")
    except urllib.error.HTTPError as e:
        print(f"Error: HTTP {e.code} — {e.reason}", file=sys.stderr)
        if e.code == 401:
            print("Check your BITBUCKET_USER and BITBUCKET_TOKEN.", file=sys.stderr)
        elif e.code == 404:
            print(f"PR #{pr_number} not found in {workspace}/{repo}.", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: {e.reason}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
