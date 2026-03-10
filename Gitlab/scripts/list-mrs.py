#!/usr/bin/env python3
"""
Lists open merge requests for the current GitLab repository.

Usage:
    python3 list-mrs.py

Output: table of open MRs (number, title, author, branch).

Requires environment variables:
    GITLAB_TOKEN — Personal Access Token (scope: api)
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request


def get_repo_info() -> tuple[str, str]:
    """Returns (host, project_path) by calling detect-repo.py."""
    script = os.path.join(os.path.dirname(__file__), "detect-repo.py")
    result = subprocess.run(
        [sys.executable, script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr, end="")
        sys.exit(1)
    data = json.loads(result.stdout)
    return data["host"], data["project_path"]


def api_get(url: str, token: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"Error: HTTP {e.code} — {e.reason}", file=sys.stderr)
        if e.code == 401:
            print("Check your GITLAB_TOKEN.", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    token = os.environ.get("GITLAB_TOKEN")
    if not token:
        print("Error: GITLAB_TOKEN must be set.", file=sys.stderr)
        print("Run python3 scripts/setup.py and fill in .claude/settings.local.json", file=sys.stderr)
        sys.exit(1)

    host, project_path = get_repo_info()
    encoded = urllib.parse.quote(project_path, safe="")

    params = urllib.parse.urlencode({"state": "opened", "per_page": 50})
    api_url = f"{host}/api/v4/projects/{encoded}/merge_requests?{params}"

    mrs = api_get(api_url, token)

    if not mrs:
        print("No open merge requests found.")
        return

    print(f"{'#':<6} {'Title':<50} {'Author':<20} {'Branch'}")
    print("-" * 100)
    for mr in mrs:
        number = mr["iid"]
        title = mr["title"][:49]
        author = mr.get("author", {}).get("name", "unknown")[:19]
        branch = mr.get("source_branch", "")
        print(f"{number:<6} {title:<50} {author:<20} {branch}")


if __name__ == "__main__":
    main()
