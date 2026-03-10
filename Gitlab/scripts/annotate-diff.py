#!/usr/bin/env python3
"""
Annotates a unified git diff with new-file line numbers.

Reads the raw diff from /tmp/pr-diff-raw-<pr_number>.txt (written by fetch-diff.py)
and writes the annotated result to /tmp/pr-diff-<pr_number>.txt.

Usage:
    python3 annotate-diff.py <mr_number>

Output format:
    Added/context lines:  {line_num:>4} │ {content}
    Removed lines:             │ {content}
    Diff headers:         as-is
"""

import sys
from typing import Optional


def annotate_diff(diff_text: str) -> str:
    lines = diff_text.splitlines()

    # First pass: find the max line number for consistent padding width
    max_line = 0
    current_line = 0
    for line in lines:
        if line.startswith("@@"):
            hunk_line = _parse_hunk_header(line)
            if hunk_line is not None:
                current_line = hunk_line - 1
        elif line.startswith("+") and not line.startswith("+++"):
            current_line += 1
            max_line = max(max_line, current_line)
        elif not line.startswith("-") and not line.startswith("---"):
            current_line += 1
            max_line = max(max_line, current_line)

    pad = len(str(max_line)) if max_line > 0 else 4
    blank = " " * pad

    # Second pass: annotate
    output = []
    current_line = 0

    for line in lines:
        # File headers (--- / +++) — pass through as-is
        if line.startswith("---") or line.startswith("+++"):
            output.append(line)

        # Hunk header (@@ ... @@) — reset line counter, pass through
        elif line.startswith("@@"):
            hunk_line = _parse_hunk_header(line)
            if hunk_line is not None:
                current_line = hunk_line - 1
            output.append(line)

        # diff --git header and index lines — pass through
        elif line.startswith("diff ") or line.startswith("index ") or line.startswith("new file") or line.startswith("deleted file"):
            output.append(line)

        # Added line (+)
        elif line.startswith("+"):
            current_line += 1
            output.append(f"{current_line:>{pad}} │ {line}")

        # Removed line (-) — blank padding, no line number
        elif line.startswith("-"):
            output.append(f"{blank} │ {line}")

        # Context line (space) — has a line number in new file
        else:
            current_line += 1
            output.append(f"{current_line:>{pad}} │ {line}")

    return "\n".join(output)


def _parse_hunk_header(line: str) -> Optional[int]:
    """
    Extracts the new-file start line from a hunk header.
    Format: @@ -old_start,old_count +new_start,new_count @@
    """
    try:
        plus_part = line.split("+")[1].split("@@")[0].strip()
        new_start = int(plus_part.split(",")[0])
        return new_start
    except (IndexError, ValueError):
        return None


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <mr_number>", file=sys.stderr)
        sys.exit(1)

    mr_number = sys.argv[1]
    in_path = f"/tmp/pr-diff-raw-{mr_number}.txt"
    out_path = f"/tmp/pr-diff-{mr_number}.txt"

    with open(in_path) as f:
        diff_input = f.read()

    if not diff_input.strip():
        print(f"Error: {in_path} is empty.", file=sys.stderr)
        sys.exit(1)

    with open(out_path, "w") as f:
        f.write(annotate_diff(diff_input))

    print(f"Annotated diff written to {out_path}")
