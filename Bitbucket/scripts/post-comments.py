#!/usr/bin/env python3
"""
Posts inline PR review comments to Bitbucket from a structured text file.

Usage:
    python3 post-comments.py <pr_number> <comments_file> <event>

    event: APPROVE | REQUEST_CHANGES | COMMENT

The comments_file uses this format (blocks separated by ---):

    Single-line:
        FILE: path/to/file.ts
        LINE: 42
        COMMENT: your review comment
        ---

    Multi-line (all lines between START and END must be + lines):
        FILE: path/to/file.ts
        START_LINE: 40
        END_LINE: 45
        COMMENT: your review comment
        ---

Special case: if the file contains only "LGTM", no comments are posted.

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
from typing import Optional


# ── Parsing ────────────────────────────────────────────────────────────────────

def parse_blocks(comments_path: str) -> list[dict]:
    with open(comments_path) as f:
        content = f.read().strip()

    if content == "LGTM":
        return []

    raw_blocks = re.split(r"\n---\n?|\n?---\n", content)
    blocks = []

    for raw in raw_blocks:
        raw = raw.strip()
        if not raw:
            continue

        fields: dict[str, str] = {}
        current_key: Optional[str] = None
        current_val_lines: list[str] = []

        for line in raw.splitlines():
            m = re.match(r"^([A-Z_]+): ?(.*)", line)
            if m:
                if current_key:
                    fields[current_key] = "\n".join(current_val_lines).strip()
                current_key = m.group(1)
                current_val_lines = [m.group(2)]
            else:
                if current_key:
                    current_val_lines.append(line)

        if current_key:
            fields[current_key] = "\n".join(current_val_lines).strip()

        if fields:
            blocks.append(fields)

    return blocks


def validate(block: dict) -> Optional[str]:
    if "FILE" not in block:
        return "missing FILE field"
    if "COMMENT" not in block:
        return "missing COMMENT field"
    if "START_LINE" in block and "END_LINE" not in block:
        return "missing END_LINE field"
    if "START_LINE" not in block and "LINE" not in block:
        return "missing LINE field"
    return None


# ── HTTP ───────────────────────────────────────────────────────────────────────

def api_request(method: str, url: str, user: str, token: str, body: Optional[dict] = None) -> dict:
    auth = base64.b64encode(f"{user}:{token}".encode()).decode()
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if data else {}),
        },
    )
    try:
        with urllib.request.urlopen(req) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        print(f"Error: HTTP {e.code} — {e.reason}", file=sys.stderr)
        print(body_text, file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: {e.reason}", file=sys.stderr)
        sys.exit(1)


# ── Git remote ─────────────────────────────────────────────────────────────────

def get_remote_url() -> str:
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Error: could not get git remote URL.", file=sys.stderr)
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


# ── Main ───────────────────────────────────────────────────────────────────────

VALID_EVENTS = {"APPROVE", "REQUEST_CHANGES", "COMMENT"}


def main() -> None:
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <pr_number> <comments_file> <event>", file=sys.stderr)
        print(f"  event: {' | '.join(sorted(VALID_EVENTS))}", file=sys.stderr)
        sys.exit(1)

    pr_number, comments_file, event = sys.argv[1], sys.argv[2], sys.argv[3]

    if event not in VALID_EVENTS:
        print(f"Error: invalid event {event!r}. Must be one of: {', '.join(sorted(VALID_EVENTS))}", file=sys.stderr)
        sys.exit(1)

    user = os.environ.get("BITBUCKET_USER")
    token = os.environ.get("BITBUCKET_TOKEN")
    if not user or not token:
        print("Error: BITBUCKET_USER and BITBUCKET_TOKEN must be set.", file=sys.stderr)
        sys.exit(1)

    blocks = parse_blocks(comments_file)

    if not blocks:
        print("LGTM — no comments to post.")
        _submit_verdict(pr_number, event, user, token, *parse_bitbucket_url(get_remote_url()))
        return

    skipped: list[tuple[int, str]] = []
    valid_blocks: list[dict] = []

    for i, block in enumerate(blocks, 1):
        reason = validate(block)
        if reason:
            skipped.append((i, reason))
            print(f"  [skip] block {i}: {reason}", file=sys.stderr)
        else:
            valid_blocks.append(block)

    remote_url = get_remote_url()
    workspace, repo = parse_bitbucket_url(remote_url)
    base = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo}/pullrequests/{pr_number}"

    posted = 0
    for block in valid_blocks:
        is_multi = "START_LINE" in block
        body_text = block['COMMENT']

        payload: dict = {"content": {"raw": body_text}}

        inline: dict = {
            "path": block["FILE"],
            "to": int(block["END_LINE"] if is_multi else block["LINE"]),
        }
        if is_multi:
            inline["start_to"] = int(block["START_LINE"])

        payload["inline"] = inline

        api_request("POST", f"{base}/comments", user, token, payload)
        posted += 1

    _submit_verdict(pr_number, event, user, token, workspace, repo)

    print(f"{posted} comment(s) posted, {len(skipped)} skipped.")
    if skipped:
        print("Skipped:")
        for i, reason in skipped:
            print(f"  Block {i}: {reason}")


def _submit_verdict(pr_number: str, event: str, user: str, token: str, workspace: str, repo: str) -> None:
    base = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo}/pullrequests/{pr_number}"

    if event == "APPROVE":
        api_request("POST", f"{base}/approve", user, token)
        print("PR approved.")
    elif event == "REQUEST_CHANGES":
        api_request("POST", f"{base}/request-changes", user, token)
        print("Changes requested.")
    # COMMENT — comments already posted individually, nothing extra needed


if __name__ == "__main__":
    main()
