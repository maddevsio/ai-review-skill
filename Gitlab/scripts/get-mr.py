#!/usr/bin/env python3
"""
Fetches merge request metadata for a GitLab MR.

Usage:
    python3 get-mr.py <mr_number>

Output (JSON, stdout):
    {
      "number": 42,
      "title": "...",
      "description": "...",
      "headRefName": "feature/my-branch",
      "baseRefName": "main",
      "headSha": "abc123...",
      "diffRefs": {"baseSha": "...", "startSha": "...", "headSha": "..."},
      "files": [{"path": "src/foo.ts", "status": "modified"}, ...]
    }

Also writes diff refs to /tmp/pr-meta-<number>.json for use by post-comments.py.

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
        elif e.code == 404:
            print("MR not found.", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: {e.reason}", file=sys.stderr)
        sys.exit(1)


STATUS_MAP = {
    "new_file": "added",
    "deleted_file": "removed",
    "renamed_file": "renamed",
}


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <mr_number>", file=sys.stderr)
        sys.exit(1)

    mr_number = sys.argv[1]

    token = os.environ.get("GITLAB_TOKEN")
    if not token:
        print("Error: GITLAB_TOKEN must be set.", file=sys.stderr)
        print("Run python3 scripts/setup.py and fill in .claude/settings.local.json", file=sys.stderr)
        sys.exit(1)

    host, project_path = get_repo_info()
    encoded = urllib.parse.quote(project_path, safe="")
    base = f"{host}/api/v4/projects/{encoded}/merge_requests/{mr_number}"

    mr = api_get(base, token)
    changes_data = api_get(f"{base}/changes", token)

    diff_refs = mr.get("diff_refs") or {}
    base_sha = diff_refs.get("base_sha", "")
    start_sha = diff_refs.get("start_sha", base_sha)
    head_sha = diff_refs.get("head_sha", mr.get("sha", ""))

    files = []
    for change in changes_data.get("changes", []):
        if change.get("deleted_file"):
            status = "removed"
        elif change.get("new_file"):
            status = "added"
        elif change.get("renamed_file"):
            status = "renamed"
        else:
            status = "modified"
        path = change.get("new_path") or change.get("old_path", "")
        if path:
            files.append({"path": path, "status": status})

    result = {
        "number": mr["iid"],
        "title": mr["title"],
        "description": mr.get("description", ""),
        "headRefName": mr["source_branch"],
        "baseRefName": mr["target_branch"],
        "headSha": head_sha,
        "diffRefs": {
            "baseSha": base_sha,
            "startSha": start_sha,
            "headSha": head_sha,
        },
        "files": files,
    }

    # Write diff refs to temp file for post-comments.py
    meta_path = f"/tmp/pr-meta-{mr_number}.json"
    with open(meta_path, "w") as f:
        json.dump(result["diffRefs"], f)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
