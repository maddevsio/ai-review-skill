#!/usr/bin/env python3
"""
Posts a PR summary as a GitHub review body (no inline comments).

Usage:
    python3 post-summary.py <pr_number> <summary_file> <event>

    event: APPROVE | REQUEST_CHANGES | COMMENT
"""

import json
import subprocess
import sys


VALID_EVENTS = {"APPROVE", "REQUEST_CHANGES", "COMMENT"}


def gh_json(*args: str) -> dict:
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def main() -> None:
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <pr_number> <summary_file> <event>", file=sys.stderr)
        print(f"  event: {' | '.join(sorted(VALID_EVENTS))}", file=sys.stderr)
        sys.exit(1)

    pr_number, summary_file, event = sys.argv[1], sys.argv[2], sys.argv[3]

    if event not in VALID_EVENTS:
        print(f"Error: invalid event {event!r}. Must be one of: {', '.join(sorted(VALID_EVENTS))}", file=sys.stderr)
        sys.exit(1)

    with open(summary_file) as f:
        summary = f.read().strip()

    repo_info = gh_json("repo", "view", "--json", "owner,name")
    owner = repo_info["owner"]["login"]
    repo = repo_info["name"]

    pr_info = gh_json("pr", "view", pr_number, "--json", "headRefOid")
    head_sha = pr_info["headRefOid"]

    body = json.dumps({
        "commit_id": head_sha,
        "event": event,
        "body": summary,
        "comments": [],
    })
    result = subprocess.run(
        [
            "gh", "api",
            f"repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            "--method", "POST",
            "--input", "-",
        ],
        input=body,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error posting summary:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    print("Summary posted as PR review.")


if __name__ == "__main__":
    main()
