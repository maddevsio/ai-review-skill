#!/usr/bin/env python3
"""
Posts inline PR review comments from a structured text file.

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
"""

import json
import re
import subprocess
import sys
from typing import Optional


def parse_blocks(comments_path: str) -> list[dict]:
    """Parse comments file into a list of field dicts."""
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
    """Return a skip reason if the block is invalid, else None."""
    if "FILE" not in block:
        return "missing FILE field"
    if "COMMENT" not in block:
        return "missing COMMENT field"
    if "START_LINE" in block and "END_LINE" not in block:
        return "missing END_LINE field"
    if "START_LINE" not in block and "LINE" not in block:
        return "missing LINE field"
    return None


def build_comment_payload(block: dict) -> dict:
    """Build a single GitHub pull review comment payload dict."""
    is_multi = "START_LINE" in block
    payload: dict = {
        "path": block["FILE"],
        "body": block["COMMENT"],
        "side": "RIGHT",
    }
    if is_multi:
        payload["start_line"] = int(block["START_LINE"])
        payload["line"] = int(block["END_LINE"])
        payload["start_side"] = "RIGHT"
    else:
        payload["line"] = int(block["LINE"])
    return payload


def gh_json(*args: str) -> dict:
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


VALID_EVENTS = {"APPROVE", "REQUEST_CHANGES", "COMMENT"}


def post_review(owner: str, repo: str, pr_number: str, head_sha: str, comments: list[dict], event: str) -> None:
    body = json.dumps({
        "commit_id": head_sha,
        "event": event,
        "body": "",
        "comments": comments,
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
        print(f"Error posting review:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <pr_number> <comments_file> <event>", file=sys.stderr)
        print(f"  event: {' | '.join(sorted(VALID_EVENTS))}", file=sys.stderr)
        sys.exit(1)

    pr_number, comments_file, event = sys.argv[1], sys.argv[2], sys.argv[3]

    if event not in VALID_EVENTS:
        print(f"Error: invalid event {event!r}. Must be one of: {', '.join(sorted(VALID_EVENTS))}", file=sys.stderr)
        sys.exit(1)

    blocks = parse_blocks(comments_file)

    if not blocks:
        print("LGTM — no comments to post.")
        return

    payloads: list[dict] = []
    skipped: list[tuple[int, str]] = []

    for i, block in enumerate(blocks, 1):
        reason = validate(block)
        if reason:
            skipped.append((i, reason))
            print(f"  [skip] block {i}: {reason}", file=sys.stderr)
        else:
            payloads.append(build_comment_payload(block))

    if not payloads:
        print(f"0 comments posted, {len(skipped)} skipped.")
        for i, reason in skipped:
            print(f"  Block {i}: {reason}")
        return

    repo_info = gh_json("repo", "view", "--json", "owner,name")
    owner = repo_info["owner"]["login"]
    repo = repo_info["name"]

    pr_info = gh_json("pr", "view", pr_number, "--json", "headRefOid")
    head_sha = pr_info["headRefOid"]

    post_review(owner, repo, pr_number, head_sha, payloads, event)

    print(f"{len(payloads)} comment(s) posted, {len(skipped)} skipped.")
    if skipped:
        print("Skipped:")
        for i, reason in skipped:
            print(f"  Block {i}: {reason}")


if __name__ == "__main__":
    main()
