#!/usr/bin/env python3
"""
Fetches the raw diff for a GitHub pull request using the gh CLI.

Writes the raw diff to /tmp/pr-diff-raw-<pr_number>.txt.
Run annotate-diff.py <pr_number> afterwards to produce the annotated diff.

Usage:
    python3 fetch-diff.py <pr_number>
"""

import subprocess
import sys


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <pr_number>", file=sys.stderr)
        sys.exit(1)

    pr_number = sys.argv[1]
    out_path = f"/tmp/pr-diff-raw-{pr_number}.txt"

    result = subprocess.run(
        ["gh", "pr", "diff", pr_number],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    with open(out_path, "w") as f:
        f.write(result.stdout)

    print(f"Raw diff written to {out_path}")


if __name__ == "__main__":
    main()
