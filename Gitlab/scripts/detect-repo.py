#!/usr/bin/env python3
"""
Detects GitLab host, namespace, and project from the git remote URL.

Usage:
    python3 detect-repo.py

Output (JSON):
    {"host": "https://gitlab.com", "project_path": "namespace/project"}

Supports:
    - https://gitlab.com/namespace/project.git
    - git@gitlab.com:namespace/project.git
    - Self-hosted: https://git.corp.com/ns/subgroup/repo.git
    - Self-hosted SSH: git@git.corp.com:ns/repo.git
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


def parse_gitlab_url(url: str) -> tuple[str, str]:
    """
    Returns (host, project_path) where host is 'https://hostname'
    and project_path is everything after the host (e.g. 'ns/subgroup/repo').
    """
    # SSH: git@hostname:path/to/repo.git
    ssh_match = re.match(r"git@([^:]+):(.+?)(?:\.git)?$", url)
    if ssh_match:
        host = f"https://{ssh_match.group(1)}"
        project_path = ssh_match.group(2)
        return host, project_path

    # HTTPS: https://hostname/path/to/repo.git
    https_match = re.match(r"(https?://[^/]+)/(.+?)(?:\.git)?$", url)
    if https_match:
        host = https_match.group(1)
        project_path = https_match.group(2)
        return host, project_path

    print(f"Error: could not parse remote URL: {url}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    url = get_remote_url()
    host, project_path = parse_gitlab_url(url)
    print(json.dumps({"host": host, "project_path": project_path}))
