#!/usr/bin/env python3
"""
Detects Bitbucket workspace and repository slug from the git remote URL.

Usage:
    python3 detect-repo.py

Output (JSON):
    {"workspace": "myworkspace", "repo": "my-repo"}
"""

import json
import re
import subprocess
import sys


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


if __name__ == "__main__":
    url = get_remote_url()
    workspace, repo = parse_bitbucket_url(url)
    print(json.dumps({"workspace": workspace, "repo": repo}))
