#!/usr/bin/env python3
"""
Fetches the raw diff for a GitLab merge request.

Reconstructs a unified diff from the /changes API response and writes it to
/tmp/pr-diff-raw-<mr_number>.txt. Run annotate-diff.py <mr_number> afterwards.

Usage:
    python3 fetch-diff.py <mr_number>

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
            print(f"MR not found.", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def build_unified_diff(changes: list[dict]) -> str:
    """
    Reconstructs a unified diff string from GitLab's changes[] array.
    Each change has old_path, new_path, new_file, deleted_file, renamed_file, diff.
    """
    parts = []
    for change in changes:
        old_path = change.get("old_path", "")
        new_path = change.get("new_path", "")
        diff_content = change.get("diff", "")

        if not diff_content:
            continue

        # Build diff --git header
        parts.append(f"diff --git a/{old_path} b/{new_path}")

        if change.get("new_file"):
            parts.append("new file mode 100644")
            parts.append(f"--- /dev/null")
            parts.append(f"+++ b/{new_path}")
        elif change.get("deleted_file"):
            parts.append("deleted file mode 100644")
            parts.append(f"--- a/{old_path}")
            parts.append("+++ /dev/null")
        else:
            parts.append(f"--- a/{old_path}")
            parts.append(f"+++ b/{new_path}")

        # diff_content from GitLab already contains hunk headers (@@ ... @@)
        parts.append(diff_content.rstrip())

    return "\n".join(parts) + "\n"


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
    url = f"{host}/api/v4/projects/{encoded}/merge_requests/{mr_number}/changes"

    data = api_get(url, token)
    changes = data.get("changes", [])

    if not changes:
        print(f"Warning: no changes found for MR #{mr_number}.", file=sys.stderr)

    unified_diff = build_unified_diff(changes)
    out_path = f"/tmp/pr-diff-raw-{mr_number}.txt"

    with open(out_path, "w") as f:
        f.write(unified_diff)

    print(f"Raw diff written to {out_path}")


if __name__ == "__main__":
    main()
