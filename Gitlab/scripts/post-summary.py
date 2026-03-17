#!/usr/bin/env python3
"""
Posts an MR summary as a GitLab note and submits a verdict.

Usage:
    python3 post-summary.py <mr_number> <summary_file> <event>

    event: APPROVE | REQUEST_CHANGES | COMMENT

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
from typing import Optional


def api_request(method: str, url: str, token: str, body: Optional[dict] = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
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


VALID_EVENTS = {"APPROVE", "REQUEST_CHANGES", "COMMENT"}


def main() -> None:
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <mr_number> <summary_file> <event>", file=sys.stderr)
        print(f"  event: {' | '.join(sorted(VALID_EVENTS))}", file=sys.stderr)
        sys.exit(1)

    mr_number, summary_file, event = sys.argv[1], sys.argv[2], sys.argv[3]

    if event not in VALID_EVENTS:
        print(f"Error: invalid event {event!r}. Must be one of: {', '.join(sorted(VALID_EVENTS))}", file=sys.stderr)
        sys.exit(1)

    token = os.environ.get("GITLAB_TOKEN")
    if not token:
        print("Error: GITLAB_TOKEN must be set.", file=sys.stderr)
        sys.exit(1)

    with open(summary_file) as f:
        summary = f.read().strip()

    host, project_path = get_repo_info()
    encoded = urllib.parse.quote(project_path, safe="")
    mr_base = f"{host}/api/v4/projects/{encoded}/merge_requests/{mr_number}"

    if event == "REQUEST_CHANGES":
        # Combine summary + verdict into one note — GitLab has no native "request changes" state.
        note_body = summary + "\n\n---\n\n⚠️ **Changes requested.** Please address the issues above before merging."
    else:
        note_body = summary

    api_request("POST", f"{mr_base}/notes", token, {"body": note_body})
    print("Summary posted as MR note.")

    if event == "APPROVE":
        api_request("POST", f"{mr_base}/approve", token)
        print("MR approved.")
    elif event == "REQUEST_CHANGES":
        print("Changes requested (posted as note — GitLab CE has no native request-changes API).")
    # COMMENT — summary already posted as note, nothing extra needed


if __name__ == "__main__":
    main()
