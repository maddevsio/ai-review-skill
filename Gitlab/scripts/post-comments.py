#!/usr/bin/env python3
"""
Posts inline MR review comments to GitLab from a structured text file.

Usage:
    python3 post-comments.py <mr_number> <comments_file> <event>

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
    GITLAB_TOKEN — Personal Access Token (scope: api)

Reads diff refs from /tmp/pr-meta-<mr_number>.json (written by get-mr.py).
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
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


# ── Helpers ────────────────────────────────────────────────────────────────────

def generate_line_code(path: str, line: int) -> str:
    """
    GitLab line code format: sha1(path)_oldLine_newLine.
    For new-file lines we use: hash_line_line.
    """
    hash_ = hashlib.sha1(path.encode()).hexdigest()
    return f"{hash_}_{line}_{line}"


# ── HTTP ───────────────────────────────────────────────────────────────────────

def api_request(
    method: str,
    url: str,
    token: str,
    body: Optional[dict] = None,
) -> dict:
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
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        print(f"Error: HTTP {e.code} — {e.reason}", file=sys.stderr)
        print(body_text, file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: {e.reason}", file=sys.stderr)
        sys.exit(1)


# ── Repo detection ─────────────────────────────────────────────────────────────

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


# ── Main ───────────────────────────────────────────────────────────────────────

VALID_EVENTS = {"APPROVE", "REQUEST_CHANGES", "COMMENT"}


def main() -> None:
    if len(sys.argv) != 4:
        print(f"Usage: {sys.argv[0]} <mr_number> <comments_file> <event>", file=sys.stderr)
        print(f"  event: {' | '.join(sorted(VALID_EVENTS))}", file=sys.stderr)
        sys.exit(1)

    mr_number, comments_file, event = sys.argv[1], sys.argv[2], sys.argv[3]

    if event not in VALID_EVENTS:
        print(f"Error: invalid event {event!r}. Must be one of: {', '.join(sorted(VALID_EVENTS))}", file=sys.stderr)
        sys.exit(1)

    token = os.environ.get("GITLAB_TOKEN")
    if not token:
        print("Error: GITLAB_TOKEN must be set.", file=sys.stderr)
        sys.exit(1)

    # Load diff refs written by get-mr.py
    meta_path = f"/tmp/pr-meta-{mr_number}.json"
    try:
        with open(meta_path) as f:
            diff_refs = json.load(f)
        base_sha = diff_refs["baseSha"]
        start_sha = diff_refs["startSha"]
        head_sha = diff_refs["headSha"]
    except FileNotFoundError:
        print(f"Error: {meta_path} not found. Run get-mr.py first.", file=sys.stderr)
        sys.exit(1)

    blocks = parse_blocks(comments_file)

    host, project_path = get_repo_info()
    encoded = urllib.parse.quote(project_path, safe="")
    mr_base = f"{host}/api/v4/projects/{encoded}/merge_requests/{mr_number}"

    if not blocks:
        print("LGTM — no comments to post.")
        _submit_verdict(mr_base, event, token, mr_number)
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

    posted = 0
    for block in valid_blocks:
        is_multi = "START_LINE" in block
        file_path = block["FILE"]
        comment_body = block["COMMENT"]

        end_line = int(block["END_LINE"] if is_multi else block["LINE"])
        start_line = int(block["START_LINE"]) if is_multi else end_line

        position: dict = {
            "position_type": "text",
            "base_sha": base_sha,
            "start_sha": start_sha,
            "head_sha": head_sha,
            "old_path": file_path,
            "new_path": file_path,
            "old_line": None,
            "new_line": end_line,
        }

        if is_multi and start_line != end_line:
            position["line_range"] = {
                "start": {
                    "line_code": generate_line_code(file_path, start_line),
                    "type": "new",
                    "old_line": None,
                    "new_line": start_line,
                },
                "end": {
                    "line_code": generate_line_code(file_path, end_line),
                    "type": "new",
                    "old_line": None,
                    "new_line": end_line,
                },
            }

        payload = {"body": comment_body, "position": position}
        api_request("POST", f"{mr_base}/discussions", token, payload)
        posted += 1

    _submit_verdict(mr_base, event, token, mr_number)

    print(f"{posted} comment(s) posted, {len(skipped)} skipped.")
    if skipped:
        print("Skipped:")
        for i, reason in skipped:
            print(f"  Block {i}: {reason}")


def _submit_verdict(mr_base: str, event: str, token: str, mr_number: str) -> None:
    if event == "APPROVE":
        api_request("POST", f"{mr_base}/approve", token)
        print("MR approved.")
    elif event == "REQUEST_CHANGES":
        # GitLab API v4 has no native "request changes" endpoint.
        # Post a general note to signal the intent.
        api_request(
            "POST",
            f"{mr_base}/notes",
            token,
            {"body": "Changes requested. Please address the review comments."},
        )
        print("Changes requested (posted as note — GitLab CE has no native request-changes API).")
    # COMMENT — inline comments already posted, nothing extra needed


if __name__ == "__main__":
    main()
